"""Smoke and regression tests for the local, provider-attributed dashboard."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from price_engine.verified.store import VerifiedPriceStore
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.workspace import create_app


class VerifiedDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "history.sqlite3"
        self.workspace = Path(self.temp.name) / "workspace.sqlite3"
        self.store = VerifiedPriceStore(self.db)
        self.client = TestClient(create_app(self.db, self.workspace))

    def tearDown(self) -> None:
        self.client.close()
        self.temp.cleanup()

    def test_empty_dashboard_never_claims_sample_prices(self) -> None:
        status = self.client.get("/api/verified/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["offers"], 0)
        self.assertEqual(status.json()["observations"], 0)
        self.assertFalse(status.json()["live_api_connected"])
        listing = self.client.get("/api/verified/offers")
        self.assertEqual(listing.json()["offers"], [])
        page = self.client.get("/verified")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Provider-reported prices", page.text)
        self.assertNotIn("3,145,728", page.text)

    def add_offer(self) -> ProviderOffer:
        quote = ProviderOffer(
            provider="SERPAPI_GOOGLE_SHOPPING", source_product_id="prod123",
            merchant="Example Shop", title="Example Backpack",
            product_url="https://example.com/item/123", currency="INR",
            price_minor=490000, stock="IN_STOCK", seller_rating=Decimal("4.4"),
            observed_at=datetime.now(timezone.utc).replace(microsecond=0),
            evidence_sha256="0" * 64, event_id=new_event_id(),
        )
        self.assertTrue(self.store.persist(quote))
        return quote

    def test_real_persisted_observations_render_in_api(self) -> None:
        quote = self.add_offer()
        listing = self.client.get("/api/verified/offers").json()["offers"]
        self.assertEqual(len(listing), 1)
        self.assertEqual(listing[0]["latest_price_minor"], 490000)
        self.assertEqual(listing[0]["stock"], "IN_STOCK")
        observations = self.client.get(
            f"/api/verified/offers/{quote.offer_id}/history").json()["observations"]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["price_minor"], 490000)
        self.assertEqual(observations[0]["provenance"], "PROVIDER_REPORTED")
        report = self.client.get(
            f"/api/verified/offers/{quote.offer_id}/analysis",
            params={"budget": "6000", "currency": "INR"})
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()["decision"], "NO_ALERT")
        self.assertFalse(report.json()["checks"]["history_depth"])

    def test_currency_mismatch_unknown_id_and_input_limits(self) -> None:
        quote = self.add_offer()
        wrong_currency = self.client.get(
            f"/api/verified/offers/{quote.offer_id}/analysis",
            params={"budget": "6000", "currency": "USD"})
        self.assertEqual(wrong_currency.status_code, 422)
        missing = self.client.get("/api/verified/offers/" + "a"*64 + "/history")
        self.assertEqual(missing.status_code, 404)
        invalid = self.client.get("/api/verified/offers", params={"limit": 10000})
        self.assertEqual(invalid.status_code, 422)

    def test_locally_served_assets(self) -> None:
        for name in ("verified.js", "verified.css"):
            result = self.client.get(f"/static/{name}")
            self.assertEqual(result.status_code, 200)


    def test_verified_studio_redesign_preserves_controls_and_provenance(self) -> None:
        from html.parser import HTMLParser
        import re

        class ElementIDs(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = []
                self.links = []
            def handle_starttag(self, tag, attrs):
                data = dict(attrs)
                if "id" in data:
                    self.ids.append(data["id"])
                if tag == "a" and "href" in data:
                    self.links.append(data["href"])

        page_response = self.client.get("/verified")
        self.assertEqual(page_response.status_code, 200)
        html = page_response.text
        parsed = ElementIDs()
        parsed.feed(html)
        js = self.client.get("/static/verified.js").text
        bound = set(re.findall(r'\$\("([a-zA-Z][a-zA-Z0-9_-]+)"\)', js))
        self.assertFalse(bound.difference(parsed.ids),
                         "Missing JavaScript-bound elements: " +
                         repr(sorted(bound.difference(parsed.ids))))
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)), "Duplicate DOM IDs")
        for control in ("search-form", "compare-form", "budget-form", "watch-form",
                        "assistant-plan-form", "assistant-confirm", "learning-enable",
                        "learning-disable", "learning-clear", "learning-prefer",
                        "learning-avoid", "learning-forget", "history-chart",
                        "intelligence-results", "watches-body", "comparison-body"):
            self.assertIn(control, parsed.ids)
        self.assertIn("Price intelligence", html)
        self.assertIn('class="sidebar"', html)
        self.assertIn('class="offer-grid"', html)
        self.assertIn("Provider-reported prices, not independently verified", html)
        self.assertIn("never start just by creating a watch", html)
        self.assertIn("/intelligence", parsed.links)
        self.assertNotIn("3,145,728", html)
        self.assertNotIn("SIMULATED_SENT", html)
        self.assertIn("function renderOfferCard(offer)", js)
        self.assertIn("a.textContent = offer.title", js)
        self.assertIn('url.protocol === "https:"', js)
        self.assertIn('rel = "noopener noreferrer"', js)
        self.assertNotIn(".innerHTML", js)
        self.assertIn('"/api/verified/search"', js)
        self.assertIn('"/api/verified/watches"', js)


if __name__ == "__main__":
    unittest.main()
