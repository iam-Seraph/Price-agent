"""Phase 5 tests: all data is local test fixtures, not a claim of real imported data."""
from __future__ import annotations

import csv
import gzip
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from price_engine.catalog_import import import_catalog
from price_engine.dashboard import create_app
from price_engine.storage import PriceStore

MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "001_initial.sql"
HEADERS = ["code", "product_name", "brands", "main_category", "quantity",
           "countries", "last_modified_t"]


class RealCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "local.sqlite3"
        store = PriceStore(self.db_path, MIGRATION)
        store.close()

    def tearDown(self):
        self.tmp.cleanup()

    def fixture(self, rows, *, compressed=True, delimiter="\t") -> Path:
        path = self.root / ("fixture.tsv.gz" if compressed else "fixture.csv")
        open_file = gzip.open if compressed else open
        with open_file(path, "wt", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=HEADERS, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_read_only_catalog_before_import(self):
        with TestClient(create_app(self.db_path)) as client:
            stats = client.get("/api/catalog/stats")
            self.assertEqual(stats.status_code, 200)
            self.assertEqual(stats.json()["products"], 0)
            self.assertFalse(stats.json()["ready"])
            self.assertFalse(client.get("/api/catalog/search").json()["ready"])
            self.assertEqual(client.get("/catalog").status_code, 200)
            self.assertEqual(client.get("/static/catalog.js").status_code, 200)
            self.assertEqual(client.post("/api/catalog/search").status_code, 405)

    def test_gzip_bulk_upsert_search_pagination_and_price_separation(self):
        input_path = self.fixture([
            {"code": "0000000012345", "product_name": "Example Oats", "brands": "Acme",
             "main_category": "Breakfast cereals", "quantity": "500 g", "countries": "India",
             "last_modified_t": "1770000000"},
            {"code": "0000000054321", "product_name": "Example Apple Juice", "brands": "Acme",
             "main_category": "Fruit juices", "quantity": "1 L", "countries": "India",
             "last_modified_t": "1770000001"},
            {"code": "bad-id", "product_name": "Invalid", "brands": "Acme"},
            {"code": "0000000033333", "product_name": "", "brands": "Acme"},
            {"code": "0000000012345", "product_name": "Example Organic Oats", "brands": "Acme",
             "main_category": "Breakfast", "last_modified_t": "1770000002"},
        ])
        result = import_catalog(input_path, self.db_path, max_rows=10,
                                batch_size=2, report_every=100)
        self.assertEqual(result["scanned_rows"], 5)
        self.assertEqual(result["accepted_rows"], 3)
        self.assertEqual(result["skipped_rows"], 2)
        self.assertEqual(result["catalog_products"], 2)
        self.assertEqual(result["prices_imported"], 0)

        with TestClient(create_app(self.db_path)) as client:
            self.assertEqual(client.get("/api/catalog/stats").json()["products"], 2)
            response = client.get("/api/catalog/search", params={"q": "Organic oats"})
            self.assertEqual(response.status_code, 200)
            entries = response.json()["items"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["name"], "Example Organic Oats")
            self.assertEqual(entries[0]["source_product_id"], "0000000012345")
            self.assertEqual(entries[0]["source_url"],
                             "https://world.openfoodfacts.org/product/0000000012345")
            self.assertNotIn("price_paisa", entries[0])
            self.assertEqual(client.get("/api/catalog/search", params={"q": "Example Oats"}).json()["items"], [])
            self.assertEqual(len(client.get("/api/catalog/search", params={"q": "oats"}).json()["items"]), 1)
            self.assertEqual(len(client.get("/api/catalog/search", params={"q": "' OR *"}).json()["items"]), 0)
            first_page = client.get("/api/catalog/search", params={"limit": 1})
            self.assertEqual(first_page.status_code, 200)
            self.assertTrue(first_page.json()["has_more"])
            next_page = client.get("/api/catalog/search", params={"limit": 1, "offset": 1})
            self.assertFalse(next_page.json()["has_more"])
            self.assertNotEqual(first_page.json()["items"][0]["source_product_id"],
                                next_page.json()["items"][0]["source_product_id"])
            self.assertEqual(client.get("/api/catalog/search", params={"limit": 101}).status_code, 422)
            self.assertEqual(client.get("/api/catalog/search", params={"offset": -1}).status_code, 422)
            self.assertEqual(client.get("/api/listings").status_code, 200)
        repeated = import_catalog(input_path, self.db_path, max_rows=10,
                                  batch_size=3, report_every=100)
        self.assertEqual(repeated["catalog_products"], 2)
        with sqlite3.connect(self.db_path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM catalog_import_runs").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM price_history").fetchone()[0], 0)

    def test_comma_csv_row_limit_and_input_validation(self):
        path = self.fixture([
            {"code": "0000000012345", "product_name": "First Food"},
            {"code": "0000000012346", "product_name": "Second Food"},
        ], compressed=False, delimiter=",")
        result = import_catalog(path, self.db_path, max_rows=1,
                                batch_size=1, report_every=100)
        self.assertEqual(result["catalog_products"], 1)
        with self.assertRaises(ValueError):
            import_catalog(path, self.db_path, max_rows=0)
        invalid_path = self.root / "bad.tsv"
        invalid_path.write_text("id\tbrand\n1\tSomething\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Expected Open Food Facts"):
            import_catalog(invalid_path, self.db_path)
        with TestClient(create_app(self.db_path)) as client:
            self.assertEqual(len(client.get("/api/catalog/search", params={"q": "Second"}).json()["items"]), 0)


if __name__ == "__main__":
    unittest.main()
