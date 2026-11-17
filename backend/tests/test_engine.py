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

    def test_unresolved_identity_fails_closed(self):
        api=FakeClient(obs()); html=FakeClient(obs(source='HTML'))
        router=HybridRouter(api,html,Policy(True,True,True),TokenBucket(600),TokenBucket(600),CircuitBreaker(),CircuitBreaker())
        result=asyncio.run(router.ingest(Listing('listing1','test','sku','https://example.org/p',None),[]))
        self.assertIsNone(result)
        self.assertEqual(api.calls,0)

    def test_storage_idempotency_and_append_only(self):
        with tempfile.TemporaryDirectory() as d:
            store=PriceStore(Path(d)/'prices.db',Path(__file__).resolve().parents[1]/'migrations/001_initial.sql')
            now='2026-11-17T00:00:00.000000Z'
            store.connection.execute('INSERT INTO products(product_id,brand,model,created_at) VALUES(?,?,?,?)',('product1','Brand','Model',now))
            store.connection.execute('INSERT INTO retailer_listings(listing_id,product_id,retailer,retailer_product_id,canonical_url,created_at) VALUES(?,?,?,?,?,?)',('listing1','product1','test','sku','https://example.org/p',now))
            self.assertTrue(store.persist(obs()))
            self.assertFalse(store.persist(obs()))
            self.assertEqual(store.accepted_prices('listing1'),[2499900])
            with self.assertRaises(sqlite3.DatabaseError):
                store.connection.execute('UPDATE price_history SET price_paisa=1')
            store.close()

if __name__=='__main__': unittest.main()
