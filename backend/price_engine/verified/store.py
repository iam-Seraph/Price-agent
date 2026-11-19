"""Atomic source-linked SQLite persistence; legacy data remains untouched."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .types import ProviderOffer

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "003_verified_offers.sql"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class VerifiedPriceStore:
    def __init__(self, path: str | Path, *, initialize: bool = True) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            with self.connect() as db:
                db.executescript("BEGIN IMMEDIATE;\n" + MIGRATION.read_text(encoding="utf-8")
                                 + "\nCOMMIT;")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.path), timeout=15)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("PRAGMA journal_mode=WAL")
            yield db
        finally:
            db.close()

    def persist(self, offer: ProviderOffer) -> bool:
        """Store one provider event. Exact replays are safe; altered replays fail."""
        if offer.observed_at.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Future-dated provider observation rejected")
        rating = str(offer.seller_rating) if offer.seller_rating is not None else None
        fields = (offer.offer_id, offer.observed_utc, offer.price_minor,
                  offer.stock, rating, offer.evidence_sha256)
        with self.connect() as db:
            with db:
                existing = db.execute(
                    "SELECT offer_id,observed_at,price_minor,stock,seller_rating,evidence_sha256 "
                    "FROM verified_offer_observations WHERE event_id=?",
                    (offer.event_id,)).fetchone()
                if existing is not None:
                    if tuple(existing) != fields:
                        raise ValueError("Event ID replay does not match immutable observation")
                    return False
                timestamp = utc_now()
                db.execute("""
                    INSERT INTO verified_offers
                    (offer_id,provider,provider_product_id,merchant,title,product_url,
                     currency,created_at,last_seen_at)
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(offer_id) DO UPDATE SET
                      title=excluded.title,product_url=excluded.product_url,
                      last_seen_at=excluded.last_seen_at
                """, (offer.offer_id,offer.provider,offer.source_product_id,offer.merchant,
                      offer.title,offer.product_url,offer.currency,timestamp,timestamp))
                db.execute("""
                    INSERT INTO verified_offer_observations
                    (event_id,offer_id,observed_at,price_minor,stock,seller_rating,
                     evidence_sha256,provenance,ingested_at)
                    VALUES(?,?,?,?,?,?,?,'PROVIDER_REPORTED',?)
                """, (offer.event_id,*fields,timestamp))
                return True

    def offer(self, offer_id: str) -> dict[str, object] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT offer_id,provider,provider_product_id,merchant,title,product_url,"
                "currency,created_at,last_seen_at FROM verified_offers WHERE offer_id=?",
                (offer_id,)).fetchone()
            return dict(row) if row else None

    def find_offers(self, query: str, currency: str, *, limit: int = 50
                    ) -> list[dict[str, object]]:
        """Query actual saved provider offers; escape SQL wildcard characters."""
        from .money import validate_currency
        if (not isinstance(query, str) or not 2 <= len(query.strip()) <= 120
                or any(ord(ch) < 32 for ch in query)):
            raise ValueError("Research query must contain 2-120 printable characters")
        currency = validate_currency(currency)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Research result limit must be 1-100")
        escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self.connect() as db:
            rows = db.execute("""
                SELECT o.offer_id,o.provider,o.provider_product_id,o.title,
                       o.merchant,o.currency,o.product_url,
                       p.observed_at,p.price_minor,p.stock,p.seller_rating,
                       p.provenance,p.evidence_sha256
                FROM verified_offers o
                JOIN verified_offer_observations p ON p.event_id=(
                    SELECT x.event_id FROM verified_offer_observations x
                    WHERE x.offer_id=o.offer_id
                    ORDER BY x.observed_at DESC,x.event_id DESC LIMIT 1
                )
                WHERE o.currency=? AND
                  (o.title LIKE ? ESCAPE '\\' COLLATE NOCASE OR
                   o.merchant LIKE ? ESCAPE '\\' COLLATE NOCASE)
                ORDER BY p.observed_at DESC,o.offer_id
                LIMIT ?
            """, (currency, "%" + escaped + "%", "%" + escaped + "%", limit)).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict[str, object]:
        """Basic local ingestion metrics, computed from actual persisted rows."""
        with self.connect() as db:
            offers = int(db.execute("SELECT COUNT(*) FROM verified_offers").fetchone()[0])
            observations = int(db.execute(
                "SELECT COUNT(*) FROM verified_offer_observations").fetchone()[0])
            latest = db.execute(
                "SELECT MAX(observed_at) FROM verified_offer_observations").fetchone()[0]
        return {"offers": offers, "observations": observations,
                "last_observed_at": latest,
                "provenance": "PROVIDER_REPORTED",
                "live_api_connected": False}

    def history(self, offer_id: str, *, days: int = 30,
                limit: int = 300) -> list[dict[str, object]]:
        """Fetch the most recent provider observations, ordered for charting."""
        if not isinstance(offer_id, str) or len(offer_id) != 64:
            raise ValueError("Valid persisted offer ID required")
        if type(days) is not int or not 1 <= days <= 365:
            raise ValueError("History lookback must be 1-365 days")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("History limit must be 1-1000")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
        with self.connect() as db:
            rows = db.execute("""
                SELECT * FROM (
                    SELECT event_id,observed_at,price_minor,stock,seller_rating,
                           evidence_sha256,provenance
                    FROM verified_offer_observations
                    WHERE offer_id=? AND observed_at>=?
                    ORDER BY observed_at DESC,event_id DESC LIMIT ?
                ) ORDER BY observed_at ASC,event_id ASC
            """, (offer_id,start,limit)).fetchall()
            return [dict(row) for row in rows]

    def list_offers(self, limit: int = 20) -> list[dict[str, object]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Limit must be between 1 and 100")
        with self.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT o.offer_id,o.merchant,o.title,o.currency,o.product_url,
                       p.observed_at AS last_observed_at,
                       p.price_minor AS latest_price_minor, p.stock,
                       p.seller_rating, p.provenance
                FROM verified_offers o JOIN verified_offer_observations p
                  ON p.event_id = (
                     SELECT p2.event_id FROM verified_offer_observations p2
                     WHERE p2.offer_id=o.offer_id
                     ORDER BY p2.observed_at DESC,p2.event_id DESC LIMIT 1
                  )
                ORDER BY p.observed_at DESC,o.offer_id LIMIT ?
            """, (limit,)).fetchall()]
