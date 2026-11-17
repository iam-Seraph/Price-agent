from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from .models import Observation, Status, Paisa

@dataclass(frozen=True, slots=True)
class PriceWindow:
    """Exact unrounded aggregates of accepted INR prices within a time window."""
    total_paisa: int
    sample_count: int
    low_paisa: Paisa | None

    def qualifies(self, current: Paisa, budget: Paisa, *,
                  in_stock: bool, seller_rating: Decimal,
                  min_samples: int = 10) -> bool:
        """At least 10% below average, within 5% of low, and all guards pass."""
        return bool(self.sample_count >= min_samples and self.low_paisa is not None
                    and current <= budget
                    and current * self.sample_count * 10 <= self.total_paisa * 9
                    and current * 20 <= self.low_paisa * 21
                    and in_stock and seller_rating.is_finite()
                    and Decimal('4.0') <= seller_rating <= Decimal('5.0'))


class PriceStore:
    def __init__(self, path: str | Path, migration: str | Path, *, initialize: bool = True) -> None:
        self.connection = sqlite3.connect(str(path), timeout=30)
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA busy_timeout=30000')
        self.connection.execute('PRAGMA journal_mode=WAL')
        if initialize:
            try:
                sql = Path(migration).read_text(encoding='utf-8')
                # executescript does not start a transaction by default.
                self.connection.executescript('BEGIN IMMEDIATE;\n' + sql + '\nCOMMIT;')
            except Exception:
                self.connection.rollback()
                self.connection.close()
                raise

    def accepted_prices(self, listing_id: str, limit: int = 30) -> list[int]:
        rows = self.connection.execute('''SELECT price_paisa FROM (
          SELECT price_paisa,observed_at FROM price_history
          WHERE listing_id=? AND validation_status='ACCEPTED' AND price_paisa IS NOT NULL
          ORDER BY observed_at DESC LIMIT ?
        ) ORDER BY observed_at ASC''', (listing_id, limit)).fetchall()
        return [int(row[0]) for row in rows]

    def price_window(self, listing_id: str, days: int = 30,
                     now: datetime | None = None) -> PriceWindow:
        if not 1 <= days <= 365:
            raise ValueError('Invalid lookback period')
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        start = (current - timedelta(days=days)).isoformat(timespec='microseconds').replace('+00:00', 'Z')
        end = current.isoformat(timespec='microseconds').replace('+00:00', 'Z')
        row = self.connection.execute('''
            SELECT COALESCE(SUM(price_paisa),0),COUNT(*),MIN(price_paisa)
            FROM price_history
            WHERE listing_id=? AND validation_status='ACCEPTED'
              AND availability='IN_STOCK' AND price_paisa IS NOT NULL
              AND observed_at>=? AND observed_at<=?
        ''', (listing_id, start, end)).fetchone()
        return PriceWindow(int(row[0]), int(row[1]),
                           Paisa(int(row[2])) if row[2] is not None else None)

    def persist(self, observation: Observation) -> bool:
        if observation.status not in (Status.VALID_PRICE, Status.OUT_OF_STOCK, Status.QUARANTINED):
            raise ValueError('Transport outcomes belong in ingestion_attempts, not price_history')
        if observation.status == Status.VALID_PRICE and (not observation.identity_verified or observation.price_paisa is None or observation.currency != 'INR' or observation.availability != 'IN_STOCK'):
            raise ValueError('Unvalidated price')
        if observation.status == Status.OUT_OF_STOCK and (not observation.identity_verified or observation.price_paisa is not None):
            raise ValueError('Unverified stock or price contradiction')
        accepted = observation.status != Status.QUARANTINED
        timestamp = datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
        with self.connection:
            cursor = self.connection.execute('''INSERT OR IGNORE INTO price_history
              (observation_id,listing_id,observed_at,ingested_at,price_paisa,availability,
               source_type,extraction_version,source_record_id,raw_payload_hash,validation_status,anomaly_reason)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
              (observation.observation_id,observation.listing_id,observation.observed_utc,timestamp,
               observation.price_paisa,observation.availability,observation.source,
               observation.extraction_version,observation.source_record_id,observation.payload_hash,
               'ACCEPTED' if accepted else 'QUARANTINED',observation.reason))
            if cursor.rowcount == 1:
                return True
            # SQLite's INSERT OR IGNORE must not hide a mutated retry payload.
            existing = self.connection.execute('''
                SELECT listing_id,source_type,source_record_id,price_paisa,
                       availability,validation_status,anomaly_reason,raw_payload_hash,
                       extraction_version,observed_at
                FROM price_history WHERE observation_id=?
            ''', (observation.observation_id,)).fetchone()
            expected = (observation.listing_id,observation.source,observation.source_record_id,
                        observation.price_paisa,observation.availability,
                        'ACCEPTED' if accepted else 'QUARANTINED',observation.reason,
                        observation.payload_hash,observation.extraction_version,
                        observation.observed_utc)
            if existing is None or tuple(existing) != expected:
                raise ValueError('Conflicting duplicate observation ID or source record')
            return False

    def close(self) -> None:
        self.connection.close()
