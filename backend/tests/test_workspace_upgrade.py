"""Offline tests for the optional dataset + product research extension."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from price_engine.product_lookup import lookup_product
from price_engine.workspace import register_workspace_routes
from price_engine.workspace_data import WorkspaceStore, parse_upload


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "workspace.sqlite3"
        app = FastAPI()
        register_workspace_routes(app, self.db)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_demo_preloaded_and_idempotent(self):
        initial = self.client.get("/api/workspace/status").json()
        self.assertEqual(initial["active"], "demo")
        self.assertEqual(initial["counts"]["demo"], 8)
        self.assertEqual(self.client.post("/api/workspace/demo").status_code, 200)
        self.assertEqual(self.client.post("/api/workspace/demo").json()["counts"]["demo"], 8)

    def test_csv_upload_and_switch(self):
        csv_bytes = b"name,price,retailer,availability,rating\nSample Item,199.99,Test Shop,IN_STOCK,4.2\n"
        response = self.client.post("/api/workspace/upload", files={"file": ("items.csv", csv_bytes, "text/csv")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["active"], "upload")
        row = self.client.get("/api/workspace/products").json()["items"][0]
        self.assertEqual(row["price_paisa"], 19999)
        self.assertEqual(row["currency"], "INR")
        self.assertEqual(self.client.post("/api/workspace/activate/demo").status_code, 200)
        self.assertEqual(self.client.post("/api/workspace/activate/upload").status_code, 200)

    def test_json_and_excel(self):
        data = json.dumps({"products": [{"name": "USB Cable", "retailer": "Demo", "price": "49.50"}]}).encode()
        self.assertEqual(parse_upload("items.json", data)[0]["price_paisa"], 4950)
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["name", "retailer", "price"])
        sheet.append(["Mouse", "Demo", 1250.5])
        stream = io.BytesIO()
        workbook.save(stream)
        self.assertEqual(parse_upload("items.xlsx", stream.getvalue())[0]["price_paisa"], 125050)

    def test_invalid_upload_does_not_replace_previous(self):
        self.client.post("/api/workspace/upload", files={"file": (
            "good.csv", b"name,price,retailer\nItem,25,Shop\n", "text/csv")})
        response = self.client.post("/api/workspace/upload", files={"file": (
            "bad.csv", b"name,price,retailer\nItem,-25,Shop\n", "text/csv")})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/workspace/status").json()["counts"]["upload"], 1)

    def test_invalid_upload_rejected(self):
        self.assertEqual(self.client.post("/api/workspace/upload", files={"file": (
            "x.txt", b"no", "text/plain")}).status_code, 422)
        self.assertEqual(self.client.post("/api/workspace/upload", files={"file": (
            "x.json", b"{}", "application/json")}).status_code, 422)
        self.assertEqual(self.client.post("/api/workspace/activate/upload").status_code, 409)

    def test_cross_origin_blocked(self):
        response = self.client.post("/api/workspace/demo", headers={"Origin": "https://example.org"})
        self.assertEqual(response.status_code, 403)

    def test_agent_offline_fallback(self):
        with patch.dict("os.environ", {"SERPAPI_KEY": ""}), patch(
            "price_engine.product_lookup.httpx.get", side_effect=RuntimeError("unexpected")
        ):
            # Unexpected programming errors should not be silently swallowed.
            with self.assertRaises(RuntimeError):
                lookup_product("Aster")
        import httpx
        with patch.dict("os.environ", {"SERPAPI_KEY": ""}), patch(
            "price_engine.product_lookup.httpx.get", side_effect=httpx.ConnectError("offline")
        ):
            result = self.client.post("/api/workspace/agent/lookup", json={"query": "Aster"})
        self.assertEqual(result.status_code, 200)
        data = result.json()
        self.assertEqual(data["provider"], "OFFLINE_DEMO")
        self.assertFalse(data["live_retailer_data"])
        self.assertFalse(data["deal_verified"])
        self.assertEqual(len(data["dataset_matches"]), 1)

    def test_untrusted_host_rejected(self):
        response = self.client.post('/api/workspace/demo', headers={
            'Host': 'attacker.example', 'Origin': 'http://attacker.example'
        })
        self.assertIn(response.status_code, (400, 403))

    def test_cross_origin_port_mismatch(self):
        response = self.client.post('/api/workspace/demo', headers={
            'Origin': 'http://testserver:65530'
        })
        self.assertEqual(response.status_code, 403)

    def test_local_dataset_persists_restart(self):
        good = b'name,retailer,price\nCable,My Store,299.25\n'
        self.assertEqual(self.client.post('/api/workspace/upload', files={
            'file': ('cables.csv', good, 'text/csv')
        }).status_code, 200)
        store2 = WorkspaceStore(self.db)
        self.assertEqual(store2.stats()['active'], 'upload')
        self.assertEqual(store2.products()['items'][0]['price_paisa'], 29925)
        store2.activate('demo')
        self.assertEqual(store2.products()['source'], 'demo')
        store2.activate('upload')
        self.assertEqual(store2.products()['source'], 'upload')

    def test_large_upload_and_overlong_columns_rejected(self):
        too_big = b'x' * (2 * 1024 * 1024 + 1)
        self.assertEqual(self.client.post('/api/workspace/upload', files={
            'file': ('big.csv', too_big, 'text/csv')
        }).status_code, 422)
        columns = ','.join('c' + str(i) for i in range(33))
        with self.assertRaisesRegex(ValueError, 'maximum 32'):
            parse_upload('columns.csv', (columns + '\n').encode())
        self.assertEqual(self.client.get('/api/workspace/status').json()['active'], 'demo')

    def test_bad_price_and_unknown_currency(self):
        for price in ('nan', 'Infinity', '-1', '0.001'):
            with self.subTest(price=price), self.assertRaises(ValueError):
                parse_upload('x.csv', f'name,retailer,price\nA,B,{price}\n'.encode())
        with self.assertRaisesRegex(ValueError, 'only INR'):
            parse_upload('x.json', json.dumps([{
                'name': 'A', 'retailer': 'B', 'price': '8', 'currency': 'USD'
            }]).encode())

    def test_paging_and_provenance(self):
        body = 'name,retailer,price\n' + ''.join(
            f'Item {i},Shop,{i}.00\n' for i in range(125))
        self.assertEqual(self.client.post('/api/workspace/upload', files={
            'file': ('many.csv', body.encode(), 'text/csv')
        }).status_code, 200)
        first = self.client.get('/api/workspace/products?limit=50&offset=0').json()
        third = self.client.get('/api/workspace/products?limit=50&offset=100').json()
        self.assertEqual(first['total'], 125)
        self.assertEqual(len(first['items']), 50)
        self.assertEqual(len(third['items']), 25)
        self.assertEqual(third['provenance'], 'USER_UPLOADED')
        self.assertEqual(third['items'][0]['name'], 'Item 100')

    def test_serpapi_error_falls_back_without_false_live_claim(self):
        import httpx
        class Response:
            def raise_for_status(self):
                pass
            def json(self):
                return {'products': [{'title': 'Headphone sample', 'price': 99,
                                      'stock': 2, 'rating': 4.2}]}
        def transport(url, **kwargs):
            if 'serpapi' in url:
                raise httpx.ConnectError('provider unavailable')
            return Response()
        with patch.dict('os.environ', {'SERPAPI_KEY': 'example'}, clear=False), patch(
            'price_engine.product_lookup.httpx.get', side_effect=transport
        ):
            result = lookup_product('Headphone')
        self.assertEqual(result['provider'], 'DUMMYJSON_SAMPLE_API')
        self.assertFalse(result['live_retailer_data'])
        self.assertTrue(result['warnings'])

    def test_serpapi_provider(self):
        class Response:
            def raise_for_status(self):
                pass
            def json(self):
                return {"shopping_results": [{"title": "Sample headset", "price": "₹2,499",
                    "extracted_price": 2499, "source": "Example Store", "rating": 4.3,
                    "reviews": 100, "in_stock": True}]}
        with patch.dict("os.environ", {"SERPAPI_KEY": "test-secret"}), patch(
            "price_engine.product_lookup.httpx.get", return_value=Response()
        ):
            data = lookup_product("headset")
        self.assertEqual(data["provider"], "SERPAPI_GOOGLE_SHOPPING")
        self.assertEqual(data["offers"][0]["currency"], "INR")
        self.assertTrue(data["live_retailer_data"])


if __name__ == "__main__":
    unittest.main()
