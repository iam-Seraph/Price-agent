from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .models import Observation, Status

class PriceStore:
    def __init__(self, path: str | Path, migration: str | Path) -> None:
        self.connection = sqlite3.connect(str(path), timeout=30)
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA busy_timeout=30000')
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.executescript(Path(migration).read_text(encoding='utf-8'))

    def accepted_prices(self, listing_id: str, limit: int = 30) -> list[int]:
        rows = self.connection.execute('''SELECT price_paisa FROM (
          SELECT price_paisa,observed_at FROM price_history
          WHERE listing_id=? AND validation_status='ACCEPTED' AND price_paisa IS NOT NULL
          ORDER BY observed_at DESC LIMIT ?
        ) ORDER BY observed_at ASC''', (listing_id, limit)).fetchall()
        return [int(row[0]) for row in rows]

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
            return cursor.rowcount == 1

    def close(self) -> None:
        self.connection.close()
