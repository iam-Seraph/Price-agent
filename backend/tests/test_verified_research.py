"""Source-attributed product research, comparison and injection regression checks."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from price_engine.verified.comparison import comparison_table
from price_engine.verified.explanations import explain_candidates
from price_engine.verified.research import research_offers
from price_engine.verified.store import VerifiedPriceStore
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.workspace import create_app


class ProductResearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "research.sqlite3"
        self.store = VerifiedPriceStore(self.db)
        self.now = datetime.now(timezone.utc)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def add(self, sku: str, merchant: str, currency: str, amount: int,
            *, stock: str = "IN_STOCK") -> ProviderOffer:
        offer = ProviderOffer(
            provider="SERPAPI_GOOGLE_SHOPPING", source_product_id=sku,
            merchant=merchant, title="Wireless headset " + sku,
            product_url="https://shop.example.com/" + sku,
            currency=currency, price_minor=amount, stock=stock,
            seller_rating=None, observed_at=self.now,
            evidence_sha256="d"*64, event_id=new_event_id(),
        )
        self.assertTrue(self.store.persist(offer))
        return offer

    def test_budget_candidates_do_not_claim_genuine_deal(self) -> None:
        self.add("one", "Store A", "INR", 200000)
        self.add("two", "Store B", "INR", 260000)
        result = research_offers(self.store, "Wireless headset", "2500",
                                 currency="INR", now=self.now)
        self.assertEqual(result["matching_offers"], 2)
        self.assertEqual(result["budget_candidates"], 1)
        for item in result["results"]:
            self.assertEqual(item["historical_deal"], "NO_ALERT")
            self.assertEqual(item["provenance"], "PROVIDER_REPORTED")
        compared = comparison_table(result)
        self.assertEqual(compared["merchant_count"], 2)
        self.assertTrue(compared["not_product_equivalence"])
        self.assertTrue(compared["rows"][0]["budget_candidate"])
        explained = explain_candidates(result)
        self.assertTrue(explained["not_a_forecast"])

    def test_currency_is_separated(self) -> None:
        self.add("usd", "US Store", "USD", 10000)
        self.add("inr", "IN Store", "INR", 150000)
        result = research_offers(self.store, "headset", "2000", currency="INR",
                                 now=self.now)
        self.assertEqual(result["matching_offers"], 1)
        self.assertEqual(result["results"][0]["currency"], "INR")

    def test_literal_search_blocks_sql_pattern_and_injection(self) -> None:
        self.add("normal", "Store", "INR", 250000)
        self.assertEqual(self.store.find_offers("%%", "INR"), [])
        self.assertEqual(self.store.find_offers("' OR 1=1 --", "INR"), [])
        self.assertEqual(len(self.store.find_offers("headset", "INR")), 1)

    def test_read_only_http_research_endpoint(self) -> None:
        self.add("one", "Store", "INR", 200000)
        client = TestClient(create_app(self.db, Path(self.tmp.name)/"workspace.sqlite3"))
        with client:
            response = client.get("/api/verified/research", params={
                "q": "headset", "budget": "2500", "currency": "INR"})
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["research"]["matching_offers"], 1)
            self.assertIn("comparison", body)
            self.assertEqual(client.get("/api/verified/research",
                params={"q": "headset", "budget": "2500",
                        "currency": "INR", "limit": 500}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
