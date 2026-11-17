from __future__ import annotations
import asyncio
import random
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4
from urllib.parse import urlparse
import httpx
from enum import StrEnum
from typing import Callable, Awaitable
from .adapters import AdapterFailure, BaseRetailerClient, Listing, current_poll_id
from .models import Observation, Status
from .validation import validate_observation
from .tool_results import PriceToolResult

def classify_failure(exc: Exception) -> Status:
    """Fail closed at the router edge; never expose raw adapter exceptions."""
    if isinstance(exc, PermissionError):
        return Status.ACCESS_DENIED
    if isinstance(exc, ValueError):
        return Status.DOM_CHANGED
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (401, 403):
            return Status.ACCESS_DENIED
        if exc.response.status_code == 429:
            return Status.API_THROTTLED
        if 500 <= exc.response.status_code < 600:
            return Status.TRANSIENT_ERROR
        return Status.DOM_CHANGED
    if isinstance(exc, (AdapterFailure, httpx.RequestError, TimeoutError,
                        ConnectionError, OSError)):
        return Status.TRANSIENT_ERROR
    return Status.UNAVAILABLE

def failure_observation(listing: Listing, source: str, exc: Exception) -> Observation:
    status = classify_failure(exc)
    return Observation(
        listing_id=listing.listing_id, status=status,
        observed_at=datetime.now(timezone.utc), source=source,
        source_record_id=f"failure:{uuid4().hex}", reason=type(exc).__name__,
    )


class BreakerState(StrEnum):
    CLOSED = 'CLOSED'
    OPEN = 'OPEN'
    HALF_OPEN = 'HALF_OPEN'

class CircuitBreaker:
    def __init__(self, threshold: int = 5, recovery_seconds: float = 120.0) -> None:
        self.threshold = threshold
        self.recovery_seconds = recovery_seconds
        self.failures = 0
        self.state = BreakerState.CLOSED
        self.opened_at = 0.0
        self._probe_active = False

    def allow(self) -> bool:
        if self.state == BreakerState.OPEN:
            if time.monotonic() - self.opened_at < self.recovery_seconds:
                return False
            self.state = BreakerState.HALF_OPEN
        if self.state == BreakerState.HALF_OPEN:
            if self._probe_active:
                return False
            self._probe_active = True
        return True

    def release_probe(self) -> None:
        """Allow a cancelled half-open probe to be retried safely."""
        self._probe_active = False

    def success(self) -> None:
        self.failures = 0
        self.state = BreakerState.CLOSED
        self._probe_active = False

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold or self.state == BreakerState.HALF_OPEN:
            self.state = BreakerState.OPEN
            self.opened_at = time.monotonic()
        self._probe_active = False

class TokenBucket:
    def __init__(self, per_minute: float, burst: float = 1.0, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        if per_minute <= 0 or burst <= 0:
            raise ValueError('Rate and burst must be positive')
        self.rate = per_minute / 60.0
        self.capacity = burst
        self.tokens = burst
        self._clock = clock
        self._sleep = sleep
        self.updated = self._clock()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self.lock:
                now = self._clock()
                self.tokens = min(self.capacity, self.tokens + max(0.0, now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / self.rate
            # Never hold the mutex while sleeping or during cancellation.
            await self._sleep(wait)

@dataclass(frozen=True)
class Policy:
    api_enabled: bool
    html_enabled: bool
    html_authorized: bool
    max_attempts: int = 3

class HybridRouter:
    def __init__(self, api: BaseRetailerClient, html: BaseRetailerClient,
                 policy: Policy, api_bucket: TokenBucket, html_bucket: TokenBucket,
                 api_breaker: CircuitBreaker, html_breaker: CircuitBreaker, *,
                 max_in_flight: int = 20, per_host_in_flight: int = 4) -> None:
        if max_in_flight <= 0 or per_host_in_flight <= 0:
            raise ValueError('Concurrent request limits must be positive')
        self._global_limit = max_in_flight
        self._host_limit = per_host_in_flight
        self._global_permits = asyncio.Semaphore(max_in_flight)
        self._host_permits: dict[str, asyncio.Semaphore] = {}
        self.api, self.html, self.policy = api, html, policy
        self.api_bucket, self.html_bucket = api_bucket, html_bucket
        self.api_breaker, self.html_breaker = api_breaker, html_breaker
        self._host_paused_until: dict[str, float] = {}
        self._dom_failures: dict[tuple[str, str], int] = {}
        self._dom_quarantined: set[tuple[str, str]] = set()

    async def _attempt(self, client: BaseRetailerClient, listing: Listing,
                       bucket: TokenBucket, breaker: CircuitBreaker) -> Observation | None:
        host = (urlparse(listing.canonical_url).hostname or '').lower()
        source = 'API' if client is self.api else 'HTML'
        key = (host, source)
        if key in self._dom_quarantined:
            return Observation(listing_id=listing.listing_id, status=Status.QUARANTINED,
                observed_at=datetime.now(timezone.utc), source=source,
                source_record_id=f'schema-quarantine:{uuid4().hex}',
                reason='ADAPTER_SCHEMA_QUARANTINED')
        remaining = self._host_paused_until.get(host, 0.0) - time.monotonic()
        if remaining > 0:
            return Observation(listing_id=listing.listing_id, status=Status.DEFERRED,
                observed_at=datetime.now(timezone.utc), source='API' if client is self.api else 'HTML',
                source_record_id=f'deferred:{uuid4().hex}', retry_after_seconds=remaining,
                reason='HOST_COOLDOWN')
        if not breaker.allow():
            return None
        try:
            for attempt in range(self.policy.max_attempts):
                await bucket.acquire()
                # Lock order is global, then host. Neither is held during
                # token waiting or retry backoff, including on cancellation.
                async with self._global_permits:
                    host_gate = self._host_permits.setdefault(
                        host, asyncio.Semaphore(self._host_limit))
                    async with host_gate:
                        try:
                            outcome = await client.fetch_price(listing)
                        except Exception as exc:
                            outcome = failure_observation(listing, source, exc)
                if outcome.listing_id != listing.listing_id:
                    # Never let an adapter associate a price with a different listing.
                    return replace(outcome, listing_id=listing.listing_id,
                                   status=Status.QUARANTINED, price_paisa=None,
                                   identity_verified=False, reason='LISTING_MISMATCH')
                if outcome.status == Status.TRANSIENT_ERROR:
                    breaker.failure()
                    if breaker.state == BreakerState.OPEN or attempt + 1 == self.policy.max_attempts:
                        return outcome
                    await asyncio.sleep(random.uniform(0, min(60, 2 ** attempt)))
                    continue
                if outcome.status == Status.API_THROTTLED:
                    self._host_paused_until[host] = time.monotonic() + max(
                        1.0, outcome.retry_after_seconds or 60.0)
                    breaker.failure()
                    return outcome  # NEVER HTML fallback
                if outcome.status == Status.ACCESS_DENIED:
                    self._host_paused_until[host] = time.monotonic() + 120.0
                    breaker.failure()
                    return outcome  # no bypass or retry
                if outcome.status == Status.DOM_CHANGED:
                    self._dom_failures[key] = self._dom_failures.get(key, 0) + 1
                    breaker.failure()
                    if self._dom_failures[key] >= 3:
                        self._dom_quarantined.add(key)
                        return replace(outcome, status=Status.QUARANTINED,
                                       price_paisa=None, reason='ADAPTER_SCHEMA_QUARANTINED')
                    return outcome
                if outcome.status == Status.UNAVAILABLE:
                    breaker.failure()
                    return outcome
                if outcome.status in (Status.VALID_PRICE, Status.OUT_OF_STOCK):
                    self._dom_failures.pop(key, None)
                breaker.success()
                return outcome
            return None

        finally:
            breaker.release_probe()

    async def ingest_tool(self, listing: Listing, history: list[int]) -> PriceToolResult:
        """Structured ReAct tool boundary; internal retries don't use agent steps."""
        return PriceToolResult.from_observation(listing.listing_id,
                                                 await self.ingest(listing, history))

    async def ingest(self, listing: Listing, history: list[int]) -> Observation | None:
        if listing.product_id is None:
            return None  # fail-closed identity mapping
        token = current_poll_id.set(uuid4().hex)
        try:
            api_result: Observation | None = None
            if self.policy.api_enabled:
                api_result = await self._attempt(self.api, listing, self.api_bucket, self.api_breaker)
                if api_result and api_result.status in (Status.VALID_PRICE, Status.OUT_OF_STOCK):
                    return validate_observation(api_result, history)
                if api_result and api_result.status in (Status.API_THROTTLED, Status.ACCESS_DENIED, Status.QUARANTINED, Status.DEFERRED):
                    return api_result
            if not (self.policy.html_enabled and self.policy.html_authorized):
                return api_result
            html_result = await self._attempt(self.html, listing, self.html_bucket, self.html_breaker)
            if html_result and html_result.status in (Status.VALID_PRICE, Status.OUT_OF_STOCK):
                return validate_observation(html_result, history)
            return html_result or api_result
        finally:
            current_poll_id.reset(token)
