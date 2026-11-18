"""Opt-in local alert rules and durable SQLite delivery outbox."""
from __future__ import annotations

import re
from decimal import Decimal

from .analysis import analyze_offer
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .watch_store import WatchStore, watch_time

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "005_alerts.sql"
_ID = re.compile(r"[0-9a-f]{32}\Z")


class AlertStore:
    def __init__(self, path: str | Path) -> None:
        self.watches = WatchStore(path)
        with self.watches.prices.connect() as db:
            db.executescript("BEGIN IMMEDIATE;\n" + MIGRATION.read_text(encoding="utf-8")
                             + "\nCOMMIT;")

    def set_channel(self, watch_id: str, channel: str,
                    *, enabled: bool = True) -> str:
        """Enable only an operator-requested global notification channel."""
        if not isinstance(watch_id, str) or not _ID.fullmatch(watch_id):
            raise ValueError("Invalid watch ID")
        if channel not in ("EMAIL", "TELEGRAM") or type(enabled) is not bool:
            raise ValueError("Unsupported alert channel or enable status")
        with self.watches.prices.connect() as db:
            with db:
                if db.execute("SELECT enabled FROM verified_watch_queries WHERE watch_id=?",
                              (watch_id,)).fetchone() is None:
                    raise ValueError("Watch must exist before enabling alerts")
                rule_id = uuid4().hex
                db.execute("""
                    INSERT INTO verified_alert_rules(rule_id,watch_id,channel,enabled,created_at)
                    VALUES(?,?,?,?,?)
                    ON CONFLICT(watch_id,channel) DO UPDATE SET enabled=excluded.enabled
                """, (rule_id,watch_id,channel,int(enabled),watch_time(datetime.now(timezone.utc))))
                found = db.execute("""
                    SELECT rule_id FROM verified_alert_rules WHERE watch_id=? AND channel=?
                """, (watch_id,channel)).fetchone()
                if not enabled:
                    db.execute("""
                        UPDATE verified_alert_outbox SET status='FAILED',last_error='Channel disabled'
                        WHERE watch_id=? AND channel=? AND status IN ('QUEUED','LEASED')
                    """, (watch_id,channel))
                return str(found["rule_id"])

    def list_rules(self, limit: int = 100) -> list[dict[str, object]]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Rule limit must be 1-200")
        with self.watches.prices.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT rule_id,watch_id,channel,enabled,created_at
                FROM verified_alert_rules ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()]


    def enqueue_if_qualified(self, watch_id: str, offer_id: str) -> int:
        """Queue deterministic ALERT decisions only; never infer missing seller facts."""
        if not isinstance(watch_id, str) or not _ID.fullmatch(watch_id):
            raise ValueError("Invalid watch ID")
        with self.watches.prices.connect() as db:
            rule = db.execute("""
                SELECT budget_minor,currency,enabled FROM verified_watch_queries
                WHERE watch_id=?
            """, (watch_id,)).fetchone()
        if rule is None or not rule["enabled"]:
            return 0
        offer = self.watches.prices.offer(offer_id)
        if offer is None or offer["currency"] != rule["currency"]:
            return 0
        budget = Decimal(int(rule["budget_minor"])) / Decimal(100)
        report = analyze_offer(self.watches.prices, offer_id, budget)
        if report["decision"] != "ALERT":
            return 0
        observed_day = str(report["last_observed_at"])[:10]
        now = datetime.now(timezone.utc)
        stamp = watch_time(now)
        count = 0
        with self.watches.prices.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                channels = db.execute("""
                    SELECT r.channel FROM verified_alert_rules r
                    JOIN verified_watch_queries w ON w.watch_id=r.watch_id
                    WHERE r.watch_id=? AND r.enabled=1 AND w.enabled=1
                """, (watch_id,)).fetchall()
                for row in channels:
                    channel = str(row["channel"])
                    pending = db.execute("""
                        SELECT 1 FROM verified_alert_outbox
                        WHERE watch_id=? AND offer_id=? AND channel=?
                          AND status IN ('QUEUED','LEASED')
                        LIMIT 1
                    """, (watch_id,offer_id,channel)).fetchone()
                    if pending:
                        continue
                    last_sent = db.execute("""
                        SELECT delivered_at FROM verified_alert_outbox
                        WHERE watch_id=? AND offer_id=? AND channel=? AND status='DELIVERED'
                        ORDER BY delivered_at DESC LIMIT 1
                    """, (watch_id,offer_id,channel)).fetchone()
                    if last_sent:
                        delivered_at = datetime.fromisoformat(
                            str(last_sent["delivered_at"]).replace("Z","+00:00"))
                        if now - delivered_at < timedelta(hours=24):
                            continue
                    cursor = db.execute("""
                        INSERT OR IGNORE INTO verified_alert_outbox
                        (delivery_id,watch_id,offer_id,channel,observed_day,
                         price_minor,currency,created_at,status,next_attempt_at)
                        VALUES(?,?,?,?,?,?,?,?,'QUEUED',?)
                    """, (uuid4().hex,watch_id,offer_id,channel,observed_day,
                          report["price_minor"],report["currency"],stamp,stamp))
                    count += cursor.rowcount
        return count


    def claim_deliveries(self, *, now: datetime | None = None,
                         limit: int = 5) -> list[dict[str, object]]:
        """Atomically lease a bounded outbox batch for a single sender."""
        if type(limit) is not int or not 1 <= limit <= 10:
            raise ValueError("Delivery limit must be 1-10")
        clock = now or datetime.now(timezone.utc)
        at = watch_time(clock)
        lease_until = watch_time(clock + timedelta(minutes=3))
        with self.watches.prices.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute("""
                    SELECT q.delivery_id,q.watch_id,q.offer_id,q.channel,
                           q.price_minor,q.currency,q.attempts
                    FROM verified_alert_outbox q
                    JOIN verified_alert_rules r ON r.watch_id=q.watch_id AND r.channel=q.channel
                    JOIN verified_watch_queries w ON w.watch_id=q.watch_id
                    WHERE r.enabled=1 AND w.enabled=1 AND q.attempts<5
                      AND q.next_attempt_at<=?
                      AND (q.status='QUEUED' OR
                           (q.status='LEASED' AND q.lease_expires_at<=?))
                    ORDER BY q.created_at,q.delivery_id LIMIT ?
                """, (at,at,limit)).fetchall()
                claimed = []
                for row in rows:
                    item = dict(row)
                    token = uuid4().hex
                    db.execute("""
                        UPDATE verified_alert_outbox SET status='LEASED',
                          lease_owner=?,lease_expires_at=? WHERE delivery_id=?
                    """, (token,lease_until,item["delivery_id"]))
                    item["lease_owner"] = token
                    claimed.append(item)
                return claimed
