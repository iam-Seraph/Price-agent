import asyncio
from contextlib import closing
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from price_engine.async_storage import AsyncPriceStore
from price_engine.models import Observation, Paisa, Status

MIGRATION=Path(__file__).resolve().parents[1]/'migrations/001_initial.sql'


class AsyncStorageTests(unittest.TestCase):
    def test_async_write_and_1000_waiter_cancellations(self):
        async def run(path):
            async with AsyncPriceStore(path,MIGRATION) as store:
                def seed():
                    with closing(sqlite3.connect(path)) as connection, connection:
                        stamp='2026-11-17T00:00:00.000000Z'
                        connection.execute('INSERT INTO products(product_id,brand,model,created_at) VALUES(?,?,?,?)',('p','Brand','Model',stamp))
                        connection.execute('INSERT INTO retailer_listings(listing_id,product_id,retailer,retailer_product_id,canonical_url,created_at) VALUES(?,?,?,?,?,?)',('l','p','test','sku','https://example.org/p',stamp))
                await store._submit(seed)
                block=threading.Event()
                entered=threading.Event()
                def slow():
                    entered.set()
                    block.wait(timeout=3)
                active=asyncio.create_task(store._submit(slow))
                await asyncio.wait_for(asyncio.to_thread(entered.wait),1)
                waiters=[asyncio.create_task(store.accepted_prices('l')) for _ in range(1000)]
                await asyncio.sleep(0)
                for task in waiters: task.cancel()
                await asyncio.wait_for(asyncio.gather(*waiters,return_exceptions=True),5)
                active.cancel()
                block.set()
                await asyncio.gather(active,return_exceptions=True)
                # The cancelled caller may finish before its worker thread.
                # The slot must return when the actual worker completes.
                await asyncio.wait_for(store._gate.acquire(),5)
                store._gate.release()
                self.assertEqual(store._gate._value,1)
                sample=Observation('l',Status.VALID_PRICE,datetime.now(timezone.utc),
                    'API','record1',price_paisa=Paisa(125000),
                    availability='IN_STOCK',identity_verified=True)
                results=await asyncio.wait_for(asyncio.gather(*(store.persist(sample) for _ in range(6))),5)
                self.assertEqual(results.count(True),1)
                self.assertEqual(results.count(False),5)
                self.assertEqual(await store.accepted_prices('l'),[125000])
            self.assertTrue(store._closed)
        with tempfile.TemporaryDirectory() as d:
            asyncio.run(asyncio.wait_for(run(Path(d)/'prices.db'),10))

if __name__=='__main__': unittest.main()
