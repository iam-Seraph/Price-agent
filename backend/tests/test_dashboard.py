"""All dashboard tests use a temporary SQLite file. No HTTP socket is used."""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from price_engine.dashboard import ReadOnlyHistory, create_app, format_paisa
from price_engine.models import Observation, Status
from price_engine.storage import PriceStore

MIGRATION=Path(__file__).resolve().parents[1]/'migrations/001_initial.sql'
UTC=timezone.utc


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'history.sqlite3'
        self.store=PriceStore(self.path,MIGRATION)
        now=datetime.now(UTC)
        timestamp=(now-timedelta(days=2)).isoformat().replace('+00:00','Z')
        with self.store.connection:
            self.store.connection.execute('INSERT INTO products(product_id,brand,model,created_at) VALUES(?,?,?,?)',('p','OnePlus','Bullets Z2',timestamp))
            for listing in ('a','b','c','d'):
                self.store.connection.execute('''INSERT INTO retailer_listings
                    (listing_id,product_id,retailer,retailer_product_id,canonical_url,created_at)
                    VALUES(?,?,?,?,?,?)''',(listing,'p','Retailer',listing,'https://example.org/dp/'+listing,timestamp))
        def add(id,status,price,days=0,verified=True):
            obs=Observation(id,status,now-timedelta(days=days), 'API',
                'record-'+id+'-'+str(days),price_paisa=price,
                availability='IN_STOCK' if price is not None else 'OUT_OF_STOCK',
                identity_verified=verified)
            return self.store.persist(obs)
        add('a',Status.VALID_PRICE,129999,days=10)
        add('a',Status.VALID_PRICE,99999,days=0)
        add('a',Status.VALID_PRICE,109999,days=31)
        add('b',Status.OUT_OF_STOCK,None)
        add('c',Status.QUARANTINED,None)
        self.app=create_app(self.path)
        self.client=TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.store.close()
        self.temp.cleanup()

    def test_current_status_and_no_quarantined_prices(self):
        response=self.client.get('/api/listings')
        self.assertEqual(response.status_code,200)
        data={r['listing_id']:r for r in response.json()['items']}
        self.assertEqual((data['a']['status'],data['a']['price_paisa'],data['a']['price_display']),
                         ('VALID_PRICE',99999,'₹999.99'))
        self.assertFalse(data['a']['stale'])
        self.assertEqual(data['a']['trend_paisa'],[129999,99999])
        for id,status in (('b','OUT_OF_STOCK'),('c','QUARANTINED'),('d','UNAVAILABLE')):
            self.assertEqual(data[id]['status'],status)
            self.assertIsNone(data[id]['price_paisa'])
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertIn("script-src 'self'",response.headers['content-security-policy'])

    def test_history_30_day_integer_statistics_and_missing(self):
        response=self.client.get('/api/listings/a/history')
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['sample_count'],2)
        self.assertEqual(data['total_paisa'],229998)
        self.assertEqual(data['average_paisa'],114999)
        self.assertEqual(data['low_paisa'],99999)
        self.assertEqual(data['low_display'],'₹999.99')
        self.assertEqual(self.client.get('/api/listings/no-such/history').status_code,404)
        self.assertEqual(self.client.get('/api/listings/a/history?days=999').status_code,422)

    def test_db_is_read_only_append_only_and_missing_file_is_not_created(self):
        self.assertEqual(self.client.post('/api/listings').status_code,405)
        reader=ReadOnlyHistory(self.path)
        with self.assertRaises(sqlite3.OperationalError):
            connection=reader._connect()
            try:
                connection.execute('DELETE FROM price_history')
            finally:
                connection.close()
        self.assertEqual(self.store.connection.execute('SELECT COUNT(*) FROM price_history').fetchone()[0],5)
        missing=Path(self.temp.name)/'does-not-exist.sqlite3'
        with TestClient(create_app(missing)) as remote:
            self.assertEqual(remote.get('/api/listings').status_code,503)
        self.assertFalse(missing.exists())

    def test_html_local_assets_and_scheduler_health(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertIn('Track every',response.text)
        self.assertIn('/static/dashboard.js',response.text)
        self.assertEqual(self.client.get('/static/dashboard.js').status_code,200)
        health=self.client.get('/api/health').json()
        self.assertTrue(health['ok'])
        self.assertEqual(health['scheduler'],'NOT_CONFIGURED')
        self.assertFalse(health['manual_trigger_available'])
        self.assertEqual(format_paisa(129999),'₹1,299.99')

if __name__=='__main__': unittest.main()
