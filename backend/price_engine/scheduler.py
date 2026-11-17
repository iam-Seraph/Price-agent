"""Optional bounded, nonoverlapping scheduler for policy-approved poll callbacks.

No retailer is enabled here. Callbacks are injected by the host application.
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Iterable

from .adapters import Listing
from .models import Observation


class PollingScheduler:
    def __init__(self, poll: Callable[[Listing], Awaitable[Observation | None]], *,
                 interval_seconds: float = 300.0, workers: int = 4,
                 max_queued: int = 100,
                 jitter: Callable[[float, float], float] = random.uniform) -> None:
        if interval_seconds <= 0 or workers <= 0 or max_queued <= 0:
            raise ValueError('Invalid scheduler bounds')
        self.poll = poll
        self.interval_seconds = interval_seconds
        self.worker_count = workers
        self.queue: asyncio.Queue[Listing] = asyncio.Queue(maxsize=max_queued)
        self._jitter = jitter
        self._pending: set[str] = set()
        self._completed: dict[str, asyncio.Event] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._periodic: list[asyncio.Task[None]] = []
        self._started = False
        self._stopping = False
        self.last_error: dict[str, str] = {}

    async def start(self) -> None:
        if self._started or self._stopping:
            raise RuntimeError('Scheduler already started or stopping')
        self._started = True
        self._workers = [asyncio.create_task(self._worker())
                         for _ in range(self.worker_count)]

    def enqueue(self, listing: Listing) -> bool:
        """Nonblocking and bounded. Reject a duplicate scheduled/in-flight poll."""
        if not self._started or self._stopping or listing.listing_id in self._pending:
            return False
        try:
            self.queue.put_nowait(listing)
        except asyncio.QueueFull:
            return False
        self._pending.add(listing.listing_id)
        self._completed[listing.listing_id] = asyncio.Event()
        return True

    async def _worker(self) -> None:
        while True:
            listing = await self.queue.get()
            try:
                await self.poll(listing)
                self.last_error.pop(listing.listing_id, None)
            except Exception as exc:
                # A failed item is recorded without terminating sibling workers.
                self.last_error[listing.listing_id] = type(exc).__name__
            finally:
                self._pending.discard(listing.listing_id)
                event = self._completed.pop(listing.listing_id, None)
                if event is not None:
                    event.set()
                self.queue.task_done()

    async def _ticker(self, listing: Listing) -> None:
        while not self._stopping:
            delay = self._jitter(0.9, 1.1) * self.interval_seconds
            await asyncio.sleep(max(0.001, delay))
            if self.enqueue(listing):
                done = self._completed.get(listing.listing_id)
                if done is not None:
                    await done.wait()  # next iteration cannot overlap this poll

    def schedule_periodic(self, listings: Iterable[Listing]) -> None:
        if not self._started or self._stopping:
            raise RuntimeError('Start scheduler first')
        self._periodic.extend(asyncio.create_task(self._ticker(listing))
                              for listing in listings)

    async def close(self, *, drain_timeout: float = 10.0) -> None:
        if self._stopping:
            return
        self._stopping = True
        for ticker in self._periodic:
            ticker.cancel()
        await asyncio.gather(*self._periodic, return_exceptions=True)
        try:
            await asyncio.wait_for(self.queue.join(), timeout=drain_timeout)
        finally:
            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()
            self._periodic.clear()
