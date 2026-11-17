"""Policy-gated JSON-LD product adapter. No access-control circumvention."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from .adapters import BaseRetailerClient, Listing
from .models import Observation, Status
from .validation import parse_inr_paisa

class StructuredHTMLClient(BaseRetailerClient):
    def __init__(self, *, allowed_domains: tuple[str, ...], enabled: bool = False, policy_approved: bool = False) -> None:
        self.domains = allowed_domains
        self.enabled = enabled
        self.policy_approved = policy_approved

    async def health_check(self) -> bool:
        return self.enabled and self.policy_approved

    def parse(self, listing: Listing, html: str, record_id: str) -> Observation:
        now = datetime.now(timezone.utc)
        digest = hashlib.sha256(html.encode()).hexdigest()
        def outcome(status: Status, **kwargs: object) -> Observation:
            return Observation(listing_id=listing.listing_id, status=status, observed_at=now,
                source='HTML', source_record_id=record_id, payload_hash=digest, **kwargs)
        soup = BeautifulSoup(html, 'html.parser')
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                obj = json.loads(script.string or script.get_text())
            except (ValueError, TypeError):
                continue
            pending = [obj]
            while pending:
                item = pending.pop()
                if isinstance(item, list):
                    pending.extend(item)
                    continue
                if not isinstance(item, dict):
                    continue
                pending.extend(item.get('@graph', []) if isinstance(item.get('@graph'), list) else [])
                types = item.get('@type', [])
                if isinstance(types, str):
                    types = [types]
                if 'Product' not in types:
                    continue
                # Explicit product identifier match: no name-based matching.
                identifiers = {str(item.get(k, '')).strip() for k in ('sku', 'productID', 'mpn')}
                if listing.retailer_product_id not in identifiers:
                    return outcome(Status.QUARANTINED, reason='IDENTITY_UNVERIFIED')
                offers = item.get('offers')
                if isinstance(offers, list):
                    offers = offers[0] if len(offers) == 1 else None
                if not isinstance(offers, dict):
                    return outcome(Status.DOM_CHANGED, reason='OFFERS_MISSING')
                availability = str(offers.get('availability', '')).lower()
                if 'outofstock' in availability:
                    return outcome(Status.OUT_OF_STOCK, availability='OUT_OF_STOCK', identity_verified=True)
                if 'instock' not in availability:
                    return outcome(Status.QUARANTINED, reason='STOCK_UNKNOWN', identity_verified=True)
                if offers.get('priceCurrency') != 'INR':
                    return outcome(Status.QUARANTINED, reason='CURRENCY_MISMATCH', identity_verified=True)
                raw = offers.get('price')
                if not isinstance(raw, (str, int)) or isinstance(raw, bool):
                    return outcome(Status.QUARANTINED, reason='PRICE_MISSING', identity_verified=True)
                try:
                    price = parse_inr_paisa(str(raw))
                except (ValueError, TypeError):
                    return outcome(Status.QUARANTINED, reason='INVALID_PRICE', identity_verified=True)
                return outcome(Status.VALID_PRICE, price_paisa=price, availability='IN_STOCK', identity_verified=True)
        return outcome(Status.DOM_CHANGED, reason='PRODUCT_JSONLD_MISSING')

    async def fetch_price(self, listing: Listing) -> Observation:
        if not self.enabled or not self.policy_approved:
            raise PermissionError('HTML extraction requires documented authorization')
        url = urlparse(listing.canonical_url)
        host = (url.hostname or '').lower()
        if url.scheme != 'https' or url.port not in (None, 443) or url.username or url.password or not any(host == d or host.endswith('.'+d) for d in self.domains):
            raise ValueError('URL outside approved HTTPS retailer domains')
        # Uses existing URL security checks; this does not make network access safe against DNS rebinding.
        from live_price import validate_url
        validate_url(listing.canonical_url)
        response = requests.get(listing.canonical_url, timeout=(5, 15), allow_redirects=False,
            headers={'User-Agent': 'PriceAgentEducational/1.0 (transparent, policy-gated)'})
        if response.status_code == 429:
            return Observation(listing_id=listing.listing_id, status=Status.API_THROTTLED,
                observed_at=datetime.now(timezone.utc), source='HTML', source_record_id='throttle:'+hashlib.sha256(listing.canonical_url.encode()).hexdigest(),
                reason='HTTP_429')
        if response.status_code in (401, 403) or 300 <= response.status_code < 400:
            return Observation(listing_id=listing.listing_id, status=Status.ACCESS_DENIED,
                observed_at=datetime.now(timezone.utc), source='HTML', source_record_id='denied:'+hashlib.sha256(listing.canonical_url.encode()).hexdigest())
        response.raise_for_status()
        if 'html' not in response.headers.get('content-type', '').lower() or len(response.content) > 3_000_000:
            raise ValueError('Unexpected response type or size')
        # A new fetch is a new observation; caller-provided idempotency key is needed for retry stability.
        return self.parse(listing, response.text, hashlib.sha256(response.content).hexdigest())
