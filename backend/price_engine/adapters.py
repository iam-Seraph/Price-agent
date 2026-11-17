from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from contextvars import ContextVar
from .models import Observation

@dataclass(frozen=True, slots=True)
class Listing:
    listing_id: str
    retailer: str
    retailer_product_id: str
    canonical_url: str
    product_id: str | None
    seller_id: str = ''

# One unique ID per logical poll; ContextVar keeps concurrent polls isolated.
current_poll_id: ContextVar[str | None] = ContextVar('price_agent_poll_id', default=None)

class BaseRetailerClient(ABC):
    @abstractmethod
    async def fetch_price(self, listing: Listing) -> Observation:
        """Return a typed outcome; never invent unavailable prices."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Non-invasive health check under retailer policy."""

class AdapterFailure(Exception):
    """Transient transport failure; safe to retry under policy."""
