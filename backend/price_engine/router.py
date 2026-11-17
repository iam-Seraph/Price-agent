from __future__ import annotations
import asyncio
import random
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Awaitable
from .adapters import AdapterFailure, BaseRetailerClient, Listing
from .models import Observation, Status
from .validation import validate_observation

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
    def __init__(self, per_minute: float, burst: float = 1.0) -> None:
        if per_minute <= 0 or burst <= 0:
            raise ValueError('Rate and burst must be positive')
        self.rate = per_minute / 60.0
        self.capacity = burst
        self.tokens = burst
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)

@dataclass(frozen=True)
class Policy:
    api_enabled: bool
    html_enabled: bool
    html_authorized: bool
    max_attempts: int = 3

class HybridRouter:
    def __init__(self, api: BaseRetailerClient, html: BaseRetailerClient,
                 policy: Policy, api_bucket: TokenBucket, html_bucket: TokenBucket,
                 api_breaker: CircuitBreaker, html_breaker: CircuitBreaker) -> None:
        self.api, self.html, self.policy = api, html, policy
        self.api_bucket, self.html_bucket = api_bucket, html_bucket
        self.api_breaker, self.html_breaker = api_breaker, html_breaker

    async def _attempt(self, client: BaseRetailerClient, listing: Listing,
                       bucket: TokenBucket, breaker: CircuitBreaker) -> Observation | None:
        if not breaker.allow():
            return None
        for attempt in range(self.policy.max_attempts):
            await bucket.acquire()
            try:
                outcome = await client.fetch_price(listing)
            except AdapterFailure:
                breaker.failure()
                if breaker.state == BreakerState.OPEN or attempt + 1 == self.policy.max_attempts:
                    return None
                await asyncio.sleep(random.uniform(0, min(60, 2 ** attempt)))
                continue
            if outcome.status == Status.TRANSIENT_ERROR:
                breaker.failure()
                if breaker.state == BreakerState.OPEN or attempt + 1 == self.policy.max_attempts:
                    return outcome
                await asyncio.sleep(random.uniform(0, min(60, 2 ** attempt)))
                continue
            if outcome.status == Status.API_THROTTLED:
                breaker.failure()
                return outcome  # scheduler handles Retry-After; NEVER HTML fallback
            if outcome.status == Status.ACCESS_DENIED:
                breaker.failure()
                return outcome  # access restrictions apply to both tiers
            breaker.success()
            return outcome
        return None

    async def ingest(self, listing: Listing, history: list[int]) -> Observation | None:
        if listing.product_id is None:
            return None  # fail-closed identity mapping
        api_result: Observation | None = None
        if self.policy.api_enabled:
            api_result = await self._attempt(self.api, listing, self.api_bucket, self.api_breaker)
            if api_result and api_result.status in (Status.VALID_PRICE, Status.OUT_OF_STOCK):
                return validate_observation(api_result, history)
            if api_result and api_result.status in (Status.API_THROTTLED, Status.ACCESS_DENIED):
                return api_result
        if not (self.policy.html_enabled and self.policy.html_authorized):
            return api_result
        html_result = await self._attempt(self.html, listing, self.html_bucket, self.html_breaker)
        if html_result and html_result.status in (Status.VALID_PRICE, Status.OUT_OF_STOCK):
            return validate_observation(html_result, history)
        return html_result or api_result
