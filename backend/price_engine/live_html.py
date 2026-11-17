"""Policy-gated JSON-LD product adapter. No access-control circumvention."""
from __future__ import annotations
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from uuid import uuid4
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from .adapters import BaseRetailerClient, Listing, current_poll_id
from .models import Observation, Status, Paisa
from .validation import parse_inr_paisa
from .network import validate_target

def record_id_for_poll(listing: Listing) -> str:
    """Stable across retries within ingest(), unique for each distinct poll."""
    return f"poll:{listing.retailer_product_id}:{current_poll_id.get() or uuid4().hex}"

class StructuredHTMLClient(BaseRetailerClient):
    def __init__(self, *, allowed_domains: tuple[str, ...], enabled: bool = False,
                 policy_approved: bool = False, http_client: httpx.AsyncClient | None = None) -> None:
        self.domains = allowed_domains
        self.enabled = enabled
        self.policy_approved = policy_approved
        # The caller owns this shared client and shuts it down at application exit.
        self.http_client = http_client

    async def health_check(self) -> bool:
        return self.enabled and self.policy_approved

    def parse(self, listing: Listing, html: str, record_id: str) -> Observation:
        now = datetime.now(timezone.utc)
        digest = hashlib.sha256(html.encode()).hexdigest()
        def outcome(status: Status, *, price_paisa: Paisa | None = None,
                    availability: str = 'UNKNOWN', identity_verified: bool = False,
                    reason: str | None = None) -> Observation:
            return Observation(listing_id=listing.listing_id, status=status, observed_at=now,
                source='HTML', source_record_id=record_id, payload_hash=digest,
                price_paisa=price_paisa, availability=availability,
                identity_verified=identity_verified, reason=reason)
        if len(html) > 3_000_000:
            return outcome(Status.DOM_CHANGED, reason='HTML_TOO_LARGE')
        soup = BeautifulSoup(html, 'html.parser')
        found_product = False
        inspected = 0
        for script in soup.select('script[type="application/ld+json"]')[:32]:
            try:
                obj = json.loads(script.string or script.get_text())
            except (ValueError, TypeError):
                continue
            pending: list[object] = [obj]
            while pending:
                inspected += 1
                if inspected > 250:
                    return outcome(Status.DOM_CHANGED, reason='JSONLD_TOO_COMPLEX')
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
                found_product = True
                # Explicit product identifier match: no name-based matching.
                identifiers = {str(item.get(k, '')).strip() for k in ('sku', 'productID', 'mpn')}
                if listing.retailer_product_id not in identifiers:
                    continue  # a later Product node may be the matching listing
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
        if found_product:
            return outcome(Status.QUARANTINED, reason='IDENTITY_UNVERIFIED')
        return outcome(Status.DOM_CHANGED, reason='PRODUCT_JSONLD_MISSING')

    async def fetch_price(self, listing: Listing) -> Observation:
        if not self.enabled or not self.policy_approved:
            raise PermissionError('HTML extraction requires documented authorization')
        url = urlparse(listing.canonical_url)
        host = (url.hostname or '').lower()
        if url.scheme != 'https' or url.port not in (None, 443) or url.username or url.password or not any(host == d or host.endswith('.'+d) for d in self.domains):
            raise ValueError('URL outside approved HTTPS retailer domains')
        if self.http_client is None:
            raise RuntimeError('Approved HTML extraction requires an injected shared AsyncClient')
        # The existing DNS check does not pin the address used for the connection.
        await asyncio.to_thread(validate_target, listing.canonical_url, self.domains)
        async with self.http_client.stream('GET', listing.canonical_url, follow_redirects=False) as response:
            if response.status_code in (429, 503, 401, 403) or 300 <= response.status_code < 400:
                return self._http_rejection(listing, response)
            response.raise_for_status()
            if 'html' not in response.headers.get('content-type', '').lower():
                raise ValueError('Unexpected response content type')
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > 3_000_000:
                    raise ValueError('HTML response too large')
                chunks.append(chunk)
            html = b''.join(chunks).decode('utf-8', errors='replace')
        return await asyncio.to_thread(self.parse, listing, html, record_id_for_poll(listing))
    def _http_rejection(self, listing: Listing, response: httpx.Response) -> Observation:
        is_throttle = (response.status_code == 429 or
                       (response.status_code == 503 and 'retry-after' in response.headers))
        status = (Status.API_THROTTLED if is_throttle else
                  Status.TRANSIENT_ERROR if response.status_code == 503 else Status.ACCESS_DENIED)
        retry_after: float | None = None
        header = response.headers.get('retry-after')
        if header and is_throttle:
            try:
                retry_after = float(header)
            except ValueError:
                try:
                    deadline = parsedate_to_datetime(header)
                    retry_after = (deadline - datetime.now(timezone.utc)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    retry_after = None
            if retry_after is not None:
                retry_after = max(0.0, min(3600.0, retry_after))
        return Observation(
            listing_id=listing.listing_id, status=status,
            observed_at=datetime.now(timezone.utc), source='HTML',
            source_record_id=record_id_for_poll(listing), reason=f'HTTP_{response.status_code}',
            retry_after_seconds=retry_after,
        )
