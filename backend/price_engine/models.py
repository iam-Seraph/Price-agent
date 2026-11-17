from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256

class Status(StrEnum):
    VALID_PRICE = 'VALID_PRICE'
    OUT_OF_STOCK = 'OUT_OF_STOCK'
    API_THROTTLED = 'API_THROTTLED'
    ACCESS_DENIED = 'ACCESS_DENIED'
    DOM_CHANGED = 'DOM_CHANGED'
    QUARANTINED = 'QUARANTINED'
    TRANSIENT_ERROR = 'TRANSIENT_ERROR'
    UNAVAILABLE = 'UNAVAILABLE'
    DEFERRED = 'DEFERRED'

@dataclass(frozen=True, slots=True)
class Observation:
    listing_id: str
    status: Status
    observed_at: datetime
    source: str
    source_record_id: str
    price_paisa: int | None = None
    currency: str = 'INR'
    payload_hash: str = ''
    availability: str = 'UNKNOWN'
    extraction_version: str = '1'
    reason: str | None = None
    retry_after_seconds: float | None = None
    identity_verified: bool = False

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError('Observed time must be timezone-aware')
        if not self.listing_id or not self.source_record_id:
            raise ValueError('Stable listing and source record IDs required')
        if self.price_paisa is not None and (type(self.price_paisa) is not int or self.price_paisa <= 0):
            raise ValueError('Price must be a positive integer of paisa')

    @property
    def observation_id(self) -> str:
        identity = '\x1f'.join((self.listing_id, self.source, self.source_record_id))
        return sha256(identity.encode('utf-8')).hexdigest()

    @property
    def observed_utc(self) -> str:
        return self.observed_at.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')
