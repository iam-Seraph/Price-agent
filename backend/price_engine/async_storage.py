"""Single-file SQLite bridge: explicit thread offload and cancellation-safe queuing.

A cancelled caller does not cancel an already-started SQLite operation; its
semaphore slot is returned only when that operation actually finishes. close()
awaits all in-flight work. No new SQLite schema or driver dependency.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar, cast

from .models import Observation
from .storage import PriceStore, PriceWindow

T = TypeVar('T')


class AsyncPriceStore:
    def __init__(self, path: str | Path, migration: str | Path) -> None:
        self.path = Path(path)
        self.migration = Path(migration)
        self._gate = asyncio.Semaphore(1)
        self._active: set[asyncio.Task[object]] = set()
        self._ready = False
        self._closed = False

    async def _submit(self, function: Callable[[], T]) -> T:
        if self._closed:
            raise RuntimeError('Store is closing')
        await self._gate.acquire()
        if self._closed:
            self._gate.release()
            raise RuntimeError('Store is closing')

        async def runner() -> object:
            return await asyncio.to_thread(function)

        try:
            task = asyncio.create_task(runner())
        except Exception:
            self._gate.release()
            raise
        self._active.add(task)

        def release(completed: asyncio.Task[object]) -> None:
            self._active.discard(completed)
            self._gate.release()

        task.add_done_callback(release)
        # Shield doesn't swallow CancelledError; task completion still releases gate.
        return cast(T, await asyncio.shield(task))

    def _operate(self, function: Callable[[PriceStore], T]) -> T:
        store = PriceStore(self.path, self.migration, initialize=False)
        try:
            return function(store)
        finally:
            store.close()

    async def initialize(self) -> None:
        def create() -> None:
            store = PriceStore(self.path, self.migration)
            store.close()

        await self._submit(create)
        self._ready = True

    async def persist(self, observation: Observation) -> bool:
        if not self._ready:
            raise RuntimeError('Call initialize() before ingesting data')
        return await self._submit(lambda: self._operate(lambda db: db.persist(observation)))

    async def accepted_prices(self, listing_id: str, limit: int = 30) -> list[int]:
        if not self._ready:
            raise RuntimeError('Call initialize() before reading data')
        return await self._submit(lambda: self._operate(lambda db: db.accepted_prices(listing_id, limit)))

    async def price_window(self, listing_id: str, days: int = 30) -> PriceWindow:
        if not self._ready:
            raise RuntimeError('Call initialize() before reading data')
        return await self._submit(lambda: self._operate(lambda db: db.price_window(listing_id, days)))

    async def close(self) -> None:
        self._closed = True
        if self._active:
            await asyncio.gather(*tuple(self._active), return_exceptions=True)

    async def __aenter__(self) -> AsyncPriceStore:
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        await self.close()
