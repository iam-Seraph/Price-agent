"""Persistent, opt-in watchlist records with bounded local schedules."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from .money import minor_units, validate_currency
from .store import VerifiedPriceStore, utc_now

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "004_watch_queries.sql"
WATCH_ID = re.compile(r"[0-9a-f]{32}\Z")


def watch_time(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Watch clock must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


class WatchStore:
    """Lightweight SQLite management; credentials are never persisted."""
    def __init__(self, path: str | Path) -> None:
        self.prices = VerifiedPriceStore(path)
        with self.prices.connect() as db:
            db.executescript("BEGIN IMMEDIATE;\n" + MIGRATION.read_text(encoding="utf-8")
                             + "\nCOMMIT;")

    def add_watch(self, query: str, budget: str, currency: str = "INR",
                  interval_minutes: int = 60,
                  *, now: datetime | None = None) -> str:
        if (not isinstance(query, str) or not 2 <= len(query.strip()) <= 120
                or any(ord(char) < 32 for char in query)):
            raise ValueError("Watch query must contain 2-120 printable characters")
        if type(interval_minutes) is not int or not 15 <= interval_minutes <= 1440:
            raise ValueError("Watch interval must be between 15 and 1440 minutes")
        currency = validate_currency(currency)
        minor = minor_units(budget, currency)
        watch_id = uuid4().hex
        created = watch_time(now) if now is not None else utc_now()
        with self.prices.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("""
                    SELECT watch_id FROM verified_watch_queries
                    WHERE enabled=1 AND query_text=? COLLATE NOCASE
                      AND currency=? AND budget_minor=? AND interval_seconds=?
                    ORDER BY created_at DESC LIMIT 1
                """, (query.strip(),currency,minor,interval_minutes*60)).fetchone()
                if existing is not None:
                    return str(existing["watch_id"])
                db.execute("""
                    INSERT INTO verified_watch_queries
                    (watch_id,query_text,currency,budget_minor,interval_seconds,
                     enabled,created_at,next_due_at)
                    VALUES(?,?,?,?,?,1,?,?)
                """, (watch_id,query.strip(),currency,minor,
                      interval_minutes*60,created,created))
        return watch_id

    def active_watch_count(self) -> int:
        """Count only enabled watches when enforcing local capacity."""
        with self.prices.connect() as db:
            return int(db.execute(
                "SELECT COUNT(*) FROM verified_watch_queries WHERE enabled=1"
            ).fetchone()[0])

    def list_watches(self, limit: int = 100) -> list[dict[str, object]]:
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Watch list limit must be 1-200")
        with self.prices.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT watch_id,query_text,currency,budget_minor,interval_seconds,
                       enabled,created_at,next_due_at,last_checked_at,last_status
                FROM verified_watch_queries
                ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()]

    def disable_watch(self, watch_id: str) -> bool:
        if not isinstance(watch_id, str) or not WATCH_ID.fullmatch(watch_id):
            raise ValueError("Invalid watch ID")
        with self.prices.connect() as db:
            with db:
                return db.execute(
                    "UPDATE verified_watch_queries SET enabled=0 WHERE watch_id=? AND enabled=1",
                    (watch_id,)).rowcount == 1


    def claim_due(self, *, now: datetime | None = None,
                  limit: int = 1) -> list[dict[str, object]]:
        """Acquire short leases under BEGIN IMMEDIATE to avoid parallel polling."""
        if type(limit) is not int or not 1 <= limit <= 5:
            raise ValueError("At most five watches may be claimed per batch")
        clock = now or datetime.now(timezone.utc)
        moment = watch_time(clock)
        expires = watch_time(clock + timedelta(minutes=10))
        with self.prices.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                due = db.execute("""
                    SELECT watch_id,query_text,currency,budget_minor,interval_seconds
                    FROM verified_watch_queries
                    WHERE enabled=1 AND next_due_at<=?
                      AND (lease_expires_at IS NULL OR lease_expires_at<=?)
                    ORDER BY next_due_at,watch_id LIMIT ?
                """, (moment,moment,limit)).fetchall()
                claimed = []
                for record in due:
                    item = dict(record)
                    item["lease_owner"] = uuid4().hex
                    db.execute("""
                        UPDATE verified_watch_queries SET lease_owner=?,lease_expires_at=?
                        WHERE watch_id=?
                    """, (item["lease_owner"],expires,item["watch_id"]))
                    claimed.append(item)
                return claimed


    def complete_claim(self, watch: dict[str, object], *, status: str,
                       offers_inspected: int, inserted_observations: int,
                       message: str = "", now: datetime | None = None) -> None:
        """Release a lease and record one sanitized monitoring attempt."""
        if status not in {"OK", "NO_MATCHES", "PROVIDER_UNAVAILABLE", "ERROR"}:
            raise ValueError("Invalid monitor status")
        if (type(offers_inspected) is not int or offers_inspected < 0
                or type(inserted_observations) is not int or inserted_observations < 0
                or inserted_observations > offers_inspected):
            raise ValueError("Invalid monitor counters")
        if not isinstance(message, str) or len(message) > 120:
            raise ValueError("Monitor audit message is too long")
        clock = now or datetime.now(timezone.utc)
        at = watch_time(clock)
        watch_id = str(watch.get("watch_id", ""))
        lease_owner = str(watch.get("lease_owner", ""))
        with self.prices.connect() as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("""
                    SELECT interval_seconds,lease_owner,created_at
                    FROM verified_watch_queries WHERE watch_id=?
                """, (watch_id,)).fetchone()
                if row is None or row["lease_owner"] != lease_owner or not lease_owner:
                    raise ValueError("Watch lease expired or belongs to another worker")
                interval = int(row["interval_seconds"])
                if status in {"PROVIDER_UNAVAILABLE", "ERROR"}:
                    interval = max(interval, 3600)
                due = watch_time(clock + timedelta(seconds=interval))
                db.execute("""
                    UPDATE verified_watch_queries SET
                      last_checked_at=?,last_status=?,next_due_at=?,
                      lease_owner=NULL,lease_expires_at=NULL
                    WHERE watch_id=?
                """, (at,status,due,watch_id))
                db.execute("""
                    INSERT INTO verified_watch_runs
                    (run_id,watch_id,started_at,completed_at,status,
                     offers_inspected,inserted_observations,message)
                    VALUES(?,?,?,?,?,?,?,?)
                """, (uuid4().hex,watch_id,str(watch.get("started_at",at)),
                      at,status,offers_inspected,inserted_observations,message))


    def recent_runs(self, *, limit: int = 30) -> list[dict[str, object]]:
        """Read bounded audit records without exposing provider credentials."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Run history limit must be 1-100")
        with self.prices.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT run_id,watch_id,started_at,completed_at,status,
                       offers_inspected,inserted_observations,message
                FROM verified_watch_runs
                ORDER BY completed_at DESC,run_id DESC LIMIT ?
            """, (limit,)).fetchall()]
