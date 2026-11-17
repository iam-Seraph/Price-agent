import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from price_engine.models import Observation, Status
from price_engine.validation import parse_inr_paisa, validate_observation
from price_engine.adapters import BaseRetailerClient, Listing
from price_engine.router import CircuitBreaker, HybridRouter, Policy, TokenBucket
from price_engine.storage import PriceStore

NOW = datetime(2026, 11, 17, tzinfo=timezone.utc)
def obs(status=Status.VALID_PRICE, price=2499900, source='API'):
    return Observation('listing1',status,NOW,source,'record-1',price_paisa=price,
        payload_hash='sha256:test',availability='IN_STOCK',identity_verified=True)

class FakeClient(BaseRetailerClient):
    def __init__(self, outcome): self.outcome=outcome; self.calls=0
    async def fetch_price(self, listing): self.calls+=1; return self.outcome
    async def health_check(self): return True

class Tests(unittest.TestCase):
    def test_prices(self):
        self.assertEqual(parse_inr_paisa('₹1,49,999.00'),14999900)
        self.assertEqual(parse_inr_paisa('INR 999.50'),99950)
        for raw in ('₹4,999/month EMI','₹2,000 off with coupon','Up to 70% off','1,234,567.00','₹0','₹12.345'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): parse_inr_paisa(raw)

    def test_integer_price_format_roundtrip_and_median_boundary(self):
        from price_engine.dashboard import format_paisa
        for paisa in range(1,10001,17):
            self.assertEqual(parse_inr_paisa(format_paisa(paisa)),paisa)
        for paisa in (1,100,9999,129999,14999950,9999999999):
            self.assertEqual(parse_inr_paisa(format_paisa(paisa)),paisa)
        # Median 100.5 paisa must not be rounded through float.
        history=[100,101]*5
        result=validate_observation(obs(price=141), history)
        self.assertEqual(result.status,Status.QUARANTINED)
        self.assertEqual(result.reason,'MEDIAN_VARIANCE_OVER_40_PERCENT')

    def test_anomaly(self):
        result=validate_observation(obs(price=450000),[1000000])
        self.assertEqual(result.status,Status.QUARANTINED)
        self.assertEqual(result.reason,'DROP_OVER_50_PERCENT')
        self.assertEqual(validate_observation(obs(price=500000),[1000000]).status,Status.VALID_PRICE)

    def test_out_of_stock(self):
        result=validate_observation(obs(Status.OUT_OF_STOCK,price=None),[])
        self.assertEqual(result.status,Status.OUT_OF_STOCK)
        self.assertEqual(validate_observation(obs(Status.OUT_OF_STOCK,price=10),[]).status,Status.QUARANTINED)

    def test_router_does_not_scrape_on_429(self):
        throttled=obs(Status.API_THROTTLED,price=None)
        api=FakeClient(throttled); html=FakeClient(obs(source='HTML'))
        router=HybridRouter(api,html,Policy(True,True,True),TokenBucket(600),TokenBucket(600),CircuitBreaker(),CircuitBreaker())
        result=asyncio.run(router.ingest(Listing('listing1','test','sku','https://example.org/p','product1'),[]))
        self.assertEqual(result.status,Status.API_THROTTLED)
        self.assertEqual(html.calls,0)

    def test_cancelled_half_open_probe_recovers(self):
        async def check():
            class HangingClient(BaseRetailerClient):
                async def fetch_price(self, listing):
                    await asyncio.sleep(100)
                async def health_check(self): return True
            async def one():
                breaker = CircuitBreaker(threshold=1, recovery_seconds=0)
                breaker.failure()
                router = HybridRouter(HangingClient(), FakeClient(obs()),
                    Policy(True, False, False), TokenBucket(60000), TokenBucket(60000),
                    breaker, CircuitBreaker())
                task = asyncio.create_task(router.ingest(
                    Listing('listing1','test','sku','https://example.org/p','product1'), []))
                await asyncio.sleep(0)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self.assertFalse(breaker._probe_active)
                self.assertTrue(breaker.allow())
                breaker.release_probe()
            await asyncio.wait_for(asyncio.gather(*(one() for _ in range(1000))), timeout=10)
        asyncio.run(check())

    def test_router_classifies_faults_and_isolates_siblings(self):
        class RaisingClient(BaseRetailerClient):
            def __init__(self, error): self.error=error; self.calls=0
            async def fetch_price(self, listing):
                self.calls+=1
                raise self.error
            async def health_check(self): return True
        cases = [
            (PermissionError('no'), Status.ACCESS_DENIED, 1),
            (ValueError('schema'), Status.DOM_CHANGED, 1),
            (TimeoutError('timeout'), Status.TRANSIENT_ERROR, 3),
            (RuntimeError('unexpected'), Status.UNAVAILABLE, 1),
        ]
        async def run():
            for error, status, count in cases:
                bad=RaisingClient(error)
                healthy=FakeClient(obs())
                router=HybridRouter(bad,FakeClient(obs(source='HTML')),
                    Policy(True,False,False),TokenBucket(60000,burst=100),
                    TokenBucket(60000),CircuitBreaker(threshold=100),CircuitBreaker())
                companion=HybridRouter(healthy,FakeClient(obs(source='HTML')),
                    Policy(True,False,False),TokenBucket(60000),TokenBucket(60000),
                    CircuitBreaker(),CircuitBreaker())
                listing=Listing('listing1','test','sku','https://example.org/p','product1')
                failed, passed=await asyncio.wait_for(asyncio.gather(
                    router.ingest(listing,[]),companion.ingest(listing,[])), timeout=5)
                self.assertEqual(failed.status,status)
                self.assertEqual(bad.calls,count)
                self.assertEqual(passed.status,Status.VALID_PRICE)
        asyncio.run(run())

    def test_rate_limiter_cancel_waiters_without_lock_leak(self):
        async def run():
            gate=asyncio.Event()
            clock=[100.0]
            async def sleep(_seconds): await gate.wait()
            bucket=TokenBucket(60,burst=1,clock=lambda:clock[0],sleep=sleep)
            await bucket.acquire()
            pending=[asyncio.create_task(bucket.acquire()) for _ in range(1000)]
            await asyncio.sleep(0)
            for task in pending: task.cancel()
            await asyncio.wait_for(asyncio.gather(*pending,return_exceptions=True),5)
            self.assertFalse(bucket.lock.locked())
            clock[0] += 1
            await asyncio.wait_for(bucket.acquire(),1)
            self.assertFalse(bucket.lock.locked())
        asyncio.run(run())

    def test_cancelled_http_permits_global_then_host_release(self):
        class HangingClient(BaseRetailerClient):
            async def health_check(self): return True
            async def fetch_price(self, listing):
                await asyncio.sleep(100)
        async def run():
            client=HangingClient()
            router=HybridRouter(client,FakeClient(obs(source='HTML')),
                Policy(True,False,False),TokenBucket(60000,burst=1200),
                TokenBucket(60000),CircuitBreaker(),CircuitBreaker(),
                max_in_flight=12,per_host_in_flight=3)
            tasks=[asyncio.create_task(router.ingest(Listing('listing1','test',
                'sku','https://example.org/p','product1'),[])) for _ in range(1000)]
            await asyncio.sleep(0)
            for task in tasks: task.cancel()
            await asyncio.wait_for(asyncio.gather(*tasks,return_exceptions=True),8)
            self.assertEqual(router._global_permits._value,12)
            self.assertEqual(router._host_permits['example.org']._value,3)
        asyncio.run(run())

    def test_repeated_dom_changes_quarantine_only_one_host(self):
        async def run():
            faulty=FakeClient(obs(Status.DOM_CHANGED,price=None))
            router=HybridRouter(faulty,FakeClient(obs(source='HTML')),
                Policy(True,False,False),TokenBucket(60000,burst=100),
                TokenBucket(60000),CircuitBreaker(threshold=100),CircuitBreaker())
            listing=Listing('listing1','test','sku','https://example.org/p','product1')
            statuses=[(await router.ingest(listing,[])).status for _ in range(4)]
            self.assertEqual(statuses,[Status.DOM_CHANGED,Status.DOM_CHANGED,
                                       Status.QUARANTINED,Status.QUARANTINED])
            self.assertEqual(faulty.calls,3)
            other=Listing('listing1','test','sku','https://another.example.net/p','product1')
            self.assertEqual((await router.ingest(other,[])).status,Status.DOM_CHANGED)
        asyncio.run(run())

    def test_host_cooldown_after_denial_and_throttle(self):
        async def run():
            for status in (Status.API_THROTTLED,Status.ACCESS_DENIED):
                rejected=FakeClient(obs(status,price=None))
                router=HybridRouter(rejected,FakeClient(obs(source='HTML')),
                    Policy(True,True,True),TokenBucket(60000,burst=100),
                    TokenBucket(60000),CircuitBreaker(),CircuitBreaker())
                target=Listing('listing1','x','sku','https://example.org/p','product1')
                first=await router.ingest(target,[])
                second=await router.ingest(target,[])
                self.assertEqual(first.status,status)
                self.assertEqual(second.status,Status.DEFERRED)
                self.assertEqual(rejected.calls,1)
                other=Listing('listing1','x','sku','https://other.example.net/p','product1')
                third=await router.ingest(other,[])
                self.assertEqual(third.status,status)
                self.assertEqual(rejected.calls,2)
        asyncio.run(run())

    def test_cross_listing_price_is_quarantined(self):
        from dataclasses import replace
        other = replace(obs(), listing_id='different')
        api=FakeClient(other)
        html=FakeClient(obs(source='HTML'))
        router=HybridRouter(api,html,Policy(True,True,True),TokenBucket(60000),
            TokenBucket(60000),CircuitBreaker(),CircuitBreaker())
        result=asyncio.run(router.ingest(Listing('listing1','test','sku',
            'https://example.org/p','product1'),[]))
        self.assertEqual((result.status,result.reason,result.listing_id,result.price_paisa),
                         (Status.QUARANTINED,'LISTING_MISMATCH','listing1',None))
        self.assertEqual(html.calls,0)
        unverified=replace(obs(Status.OUT_OF_STOCK,price=None),identity_verified=False)
        self.assertEqual(validate_observation(unverified,[]).status,Status.QUARANTINED)

    def test_separate_identical_polls_are_preserved_and_retries_are_stable(self):
        from price_engine.live_html import StructuredHTMLClient, record_id_for_poll
        from price_engine.adapters import current_poll_id
        html = '<script type="application/ld+json">{"@type":"Product","sku":"sku","offers":{"price":"1000","priceCurrency":"INR","availability":"https://schema.org/InStock"}}</script>'
        parser=StructuredHTMLClient(allowed_domains=('example.org',))
        listing=Listing('listing1','test','sku','https://example.org/p','product1')
        class ParsingClient(BaseRetailerClient):
            def __init__(self): self.ids=[]
            async def health_check(self): return True
            async def fetch_price(self, listing):
                poll=current_poll_id.get()
                self.ids.append(poll)
                self.ids.append(current_poll_id.get())
                return parser.parse(listing,html,record_id_for_poll(listing))
        client=ParsingClient()
        router=HybridRouter(client,FakeClient(obs(source='HTML')),
            Policy(True,False,False),TokenBucket(60000),TokenBucket(60000),
            CircuitBreaker(),CircuitBreaker())
        async def run():
            return [await router.ingest(listing,[]) for _ in range(2)]
        first,second=asyncio.run(run())
        self.assertEqual(first.status,Status.VALID_PRICE)
        self.assertNotEqual(first.observation_id,second.observation_id)
        self.assertEqual(client.ids[0],client.ids[1])
        self.assertEqual(client.ids[2],client.ids[3])
        self.assertNotEqual(client.ids[0],client.ids[2])
        with tempfile.TemporaryDirectory() as d:
            store=PriceStore(Path(d)/'prices.db',Path(__file__).resolve().parents[1]/'migrations/001_initial.sql')
            now='2026-11-17T00:00:00.000000Z'
            store.connection.execute('INSERT INTO products(product_id,brand,model,created_at) VALUES(?,?,?,?)',('product1','Brand','Model',now))
            store.connection.execute('INSERT INTO retailer_listings(listing_id,product_id,retailer,retailer_product_id,canonical_url,created_at) VALUES(?,?,?,?,?,?)',('listing1','product1','test','sku','https://example.org/p',now))
            self.assertTrue(store.persist(first))
            self.assertTrue(store.persist(second))
            self.assertFalse(store.persist(first))
            self.assertEqual(len(store.accepted_prices('listing1')),2)
            store.close()

    def test_unresolved_identity_fails_closed(self):
        api=FakeClient(obs()); html=FakeClient(obs(source='HTML'))
        router=HybridRouter(api,html,Policy(True,True,True),TokenBucket(600),TokenBucket(600),CircuitBreaker(),CircuitBreaker())
        result=asyncio.run(router.ingest(Listing('listing1','test','sku','https://example.org/p',None),[]))
        self.assertIsNone(result)
        self.assertEqual(api.calls,0)

    def test_structured_tool_results_all_statuses_exhaustive(self):
        from price_engine.tool_results import PriceToolResult,format_paisa
        from price_engine.models import Paisa
        self.assertEqual(format_paisa(Paisa(14999950)),'₹1,49,999.50')
        self.assertEqual(PriceToolResult.from_observation('listing1',None).error,'NO_APPROVED_SOURCE')
        for status in Status:
            price=Paisa(129999) if status == Status.VALID_PRICE else None
            result=PriceToolResult.from_observation('listing1',obs(status,price=price))
            self.assertEqual(result.ok,status==Status.VALID_PRICE)
            self.assertEqual(result.price_paisa,price if result.ok else None)
            self.assertEqual(result.price_display,'₹1,299.99' if result.ok else None)
            self.assertEqual(result.to_dict()['retryable'],status in (
                Status.API_THROTTLED,Status.TRANSIENT_ERROR,Status.DEFERRED))
        router=HybridRouter(FakeClient(obs()),FakeClient(obs(source='HTML')),
                Policy(True,False,False),TokenBucket(60000),TokenBucket(60000),
                CircuitBreaker(),CircuitBreaker())
        result=asyncio.run(router.ingest_tool(Listing('listing1','test','sku',
            'https://example.org/p','product1'),[]))
        self.assertEqual(result.price_display,'₹24,999.00')

    def test_real_30_day_window_exact_deal_arithmetic(self):
        from decimal import Decimal
        from datetime import timedelta
        from price_engine.models import Paisa
        from price_engine.storage import PriceWindow
        with tempfile.TemporaryDirectory() as d:
            store=PriceStore(Path(d)/'prices.db',Path(__file__).resolve().parents[1]/'migrations/001_initial.sql')
            now=datetime(2026,11,17,12,tzinfo=timezone.utc)
            stamp='2026-11-17T00:00:00.000000Z'
            with store.connection:
                store.connection.execute('INSERT INTO products(product_id,brand,model,created_at) VALUES(?,?,?,?)',('product1','Brand','Model',stamp))
                store.connection.execute('INSERT INTO retailer_listings(listing_id,product_id,retailer,retailer_product_id,canonical_url,created_at) VALUES(?,?,?,?,?,?)',('listing1','product1','test','sku','https://example.org/p',stamp))
            for n,days in enumerate((1,2,3,31)):
                sample=Observation('listing1',Status.VALID_PRICE,now-timedelta(days=days),
                    'API',f'r{n}',price_paisa=Paisa(10000),availability='IN_STOCK',identity_verified=True)
                store.persist(sample)
            window=store.price_window('listing1',now=now)
            self.assertEqual((window.total_paisa,window.sample_count,window.low_paisa),
                             (30000,3,10000))
            self.assertTrue(window.qualifies(Paisa(9000),Paisa(9500),in_stock=True,
                          seller_rating=Decimal('4.0'),min_samples=3))
            self.assertFalse(window.qualifies(Paisa(9001),Paisa(9500),in_stock=True,
                          seller_rating=Decimal('4.0'),min_samples=3))
            self.assertFalse(window.qualifies(Paisa(9000),Paisa(9500),in_stock=True,
                          seller_rating=Decimal('3.9'),min_samples=3))
            # Exact fractional average: 95 is not >=10% below mean 105.
            self.assertFalse(PriceWindow(105,1,Paisa(95)).qualifies(
                Paisa(95),Paisa(100),in_stock=True,
                seller_rating=Decimal('4.5'),min_samples=1))
            store.close()

    def test_schema_initialization_rolls_back_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'bad-schema.db'
            migration=Path(d)/'bad.sql'
            migration.write_text('CREATE TABLE first_table(x INTEGER);\nBROKEN SQL;')
            with self.assertRaises(sqlite3.DatabaseError):
                PriceStore(path,migration)
            with sqlite3.connect(path) as connection:
                tables=connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='first_table'").fetchall()
            self.assertEqual(tables,[])

    def test_storage_idempotency_and_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            store=PriceStore(Path(d)/'prices.db',Path(__file__).resolve().parents[1]/'migrations/001_initial.sql')
            now='2026-11-17T00:00:00.000000Z'
            store.connection.execute('INSERT INTO products(product_id,brand,model,created_at) VALUES(?,?,?,?)',('product1','Brand','Model',now))
            store.connection.execute('INSERT INTO retailer_listings(listing_id,product_id,retailer,retailer_product_id,canonical_url,created_at) VALUES(?,?,?,?,?,?)',('listing1','product1','test','sku','https://example.org/p',now))
            self.assertTrue(store.persist(obs()))
            self.assertFalse(store.persist(obs()))
            from dataclasses import replace
            with self.assertRaisesRegex(ValueError,'Conflicting duplicate'):
                store.persist(replace(obs(), price_paisa=1))
            self.assertEqual(store.accepted_prices('listing1'),[2499900])
            with self.assertRaises(sqlite3.DatabaseError):
                store.connection.execute('UPDATE price_history SET price_paisa=1')
            store.close()

if __name__=='__main__': unittest.main()
