"""End-to-end local dashboard tests without making external API calls."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.workspace import create_app


def source_quote() -> ProviderOffer:
    return ProviderOffer(
        provider="SERPAPI_GOOGLE_SHOPPING", source_product_id="headphones",
        merchant="Research Store", title="Example Bluetooth Headphones",
        product_url="https://store.example.com/p/headphones",
        currency="INR", price_minor=299900, stock="UNKNOWN",
        seller_rating=None, observed_at=datetime.now(timezone.utc),
        evidence_sha256="c" * 64, event_id=new_event_id(),
    )


class UnifiedDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        db = Path(self.temp.name) / "history.sqlite3"
        workspace = Path(self.temp.name) / "workspace.sqlite3"
        self.client = TestClient(create_app(db, workspace))
        self.headers = {"Origin": "http://testserver"}

    def tearDown(self) -> None:
        self.client.close()
        self.temp.cleanup()

    def test_provider_search_and_history_are_persisted(self) -> None:
        quote = source_quote()
        with patch("price_engine.verified.api.search_serpapi", return_value=[quote]) as provider:
            res = self.client.post("/api/verified/search", json={
                "query": "bluetooth headphones", "budget": "3500",
                "currency": "INR", "limit": 1
            }, headers=self.headers)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["inserted"], 1)
        provider.assert_called_once()
        self.assertEqual(res.json()["analyses"][0]["decision"], "NO_ALERT")
        self.assertFalse(res.json()["analyses"][0]["checks"]["stock_confirmed"])
        listing = self.client.get("/api/verified/offers").json()["offers"]
        self.assertEqual(len(listing), 1)
        history = self.client.get(
            f"/api/verified/offers/{listing[0]['offer_id']}/history").json()
        self.assertEqual(history["observations"][0]["price_minor"], 299900)

    def test_provider_search_is_rate_limited(self) -> None:
        with patch("price_engine.verified.api.search_serpapi", return_value=[]):
            data = {"query": "headphones", "budget": "3500", "currency": "INR"}
            first = self.client.post("/api/verified/search", json=data, headers=self.headers)
            second = self.client.post("/api/verified/search", json=data, headers=self.headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_browser_write_origin_validation(self) -> None:
        payload = {"query": "usb keyboard", "budget": "2000", "currency": "INR"}
        self.assertEqual(self.client.post("/api/verified/watches",
                         json=payload).status_code, 403)
        self.assertEqual(self.client.post("/api/verified/watches",
                         json=payload, headers={"Origin": "https://evil.example.com"}).status_code, 403)
        self.assertEqual(self.client.get("/api/verified/watches").json()["watches"], [])

    def test_watch_and_consent_controls_are_explicit(self) -> None:
        payload = {"query": "usb keyboard", "budget": "2000",
                   "currency": "INR", "interval_minutes": 60}
        created = self.client.post("/api/verified/watches", json=payload,
                                   headers=self.headers)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertFalse(created.json()["polling_started"])
        watch_id = created.json()["watch_id"]
        rules = self.client.get("/api/verified/watches").json()["watches"]
        self.assertEqual(len(rules), 1)
        attempted = self.client.post("/api/verified/alerts/channel", json={
            "watch_id": watch_id, "channel": "TELEGRAM",
            "enabled": True, "confirmed": False
        }, headers=self.headers)
        self.assertEqual(attempted.status_code, 422)
        agreed = self.client.post("/api/verified/alerts/channel", json={
            "watch_id": watch_id, "channel": "TELEGRAM",
            "enabled": True, "confirmed": True
        }, headers=self.headers)
        self.assertEqual(agreed.status_code, 200, agreed.text)
        self.assertFalse(agreed.json()["delivery_started"])
        self.assertEqual(len(self.client.get("/api/verified/alerts").json()["rules"]), 1)
        disabled = self.client.post(
            f"/api/verified/watches/{watch_id}/disable", headers=self.headers)
        self.assertEqual(disabled.status_code, 200)
        self.assertTrue(disabled.json()["disabled"])

    def test_simulator_is_still_explicitly_labeled(self) -> None:
        self.assertIn("SIMULATION MODE", self.client.get("/intelligence").text)
        page = self.client.get("/verified")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Search real provider offers", page.text)
        self.assertIn("opt-in alerts", page.text)


if __name__ == "__main__":
    unittest.main()
