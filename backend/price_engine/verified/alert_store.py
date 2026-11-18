"""Opt-in local alert rules and durable SQLite delivery outbox."""
from __future__ import annotations

import re
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
