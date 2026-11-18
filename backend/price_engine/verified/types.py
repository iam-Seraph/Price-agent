"""Validated, provider-reported offers and their immutable observation metadata."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import uuid4

from .money import validate_currency

_HEX64 = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9._:/+-]{1,200}\Z")


def safe_evidence_url(value: str) -> str:
    """Validate display-only URLs; never use this field for HTTP fetching."""
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Invalid evidence URL")
    parts = urlsplit(value)
    host = (parts.hostname or "").lower().rstrip(".")
    if (parts.scheme != "https" or not host or parts.username or parts.password
            or parts.port not in (None, 443) or host == "localhost"
            or host.endswith(".localhost") or host.endswith(".local")):
        raise ValueError("Only public HTTPS product links are accepted")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if "." not in host or any(not part for part in host.split(".")):
            raise ValueError("Evidence URL needs a public domain") from None
    else:
        raise ValueError("IP-literal evidence URLs are not accepted")
    return value


@dataclass(frozen=True, slots=True)
class ProviderOffer:
    provider: str
    source_product_id: str
    merchant: str
    title: str
    product_url: str
    currency: str
    price_minor: int
    stock: str
    seller_rating: Decimal | None
    observed_at: datetime
    evidence_sha256: str
    event_id: str

    def __post_init__(self) -> None:
        if self.provider != "SERPAPI_GOOGLE_SHOPPING":
            raise ValueError("Unknown price evidence provider")
        if not _ID.fullmatch(self.source_product_id):
            raise ValueError("Provider product identity missing or invalid")
        if not isinstance(self.merchant, str) or not 1 <= len(self.merchant.strip()) <= 120:
            raise ValueError("Merchant identity required")
        if not isinstance(self.title, str) or not 1 <= len(self.title.strip()) <= 300:
            raise ValueError("Product name required")
        safe_evidence_url(self.product_url)
        validate_currency(self.currency)
        if type(self.price_minor) is not int or not 1 <= self.price_minor <= 10**12:
            raise ValueError("Price must be in exact positive minor units")
        if self.stock not in {"IN_STOCK", "OUT_OF_STOCK", "UNKNOWN"}:
            raise ValueError("Invalid stock evidence")
        if (self.seller_rating is not None
                and (not isinstance(self.seller_rating, Decimal)
                     or not self.seller_rating.is_finite()
                     or not Decimal("0") <= self.seller_rating <= Decimal("5"))):
            raise ValueError("Invalid seller rating evidence")
        if (not isinstance(self.observed_at, datetime)
                or self.observed_at.tzinfo is None
                or self.observed_at.utcoffset() is None):
            raise ValueError("Observation timestamp must include timezone")
        if not _HEX64.fullmatch(self.evidence_sha256):
            raise ValueError("SHA-256 evidence fingerprint required")
        if not isinstance(self.event_id, str) or not re.fullmatch(r"[a-f0-9]{32}", self.event_id):
            raise ValueError("Invalid event identity")

    @property
    def offer_id(self) -> str:
        key = "\x1f".join((self.provider, self.source_product_id, self.merchant.casefold(),
                            self.currency)).encode("utf-8")
        return sha256(key).hexdigest()

    @property
    def observed_utc(self) -> str:
        return self.observed_at.astimezone(timezone.utc).isoformat(
            timespec="microseconds").replace("+00:00", "Z")


def new_event_id() -> str:
    return uuid4().hex
