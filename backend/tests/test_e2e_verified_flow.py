"""Full source-attributed local workflow smoke test; every external service is mocked.

This regression verifies: watched real-provider-shaped offer -> SQLite -> queued
alert -> deterministic comparison -> historical intelligence -> read-only audit
-> local API -> mocked delivery. It does not certify live merchant facts.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from price_engine.verified.alert_store import AlertStore
from price_engine.verified.audit import audit_store
from price_engine.verified.cli import main as provider_cli
from price_engine.verified.delivery import deliver_due
from price_engine.verified.intelligence import daily_series, price_trend
from price_engine.verified.monitor import run_due_once
from price_engine.verified.research import research_offers
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.verified.watch_store import WatchStore
from price_engine.workspace import create_app


def source_quote(at: datetime, price_minor: int) -> ProviderOffer:
    return ProviderOffer(
        provider="SERPAPI_GOOGLE_SHOPPING", source_product_id="test-sku-001",
        merchant="Fixture Merchant", title="USB Charger Model X",
        product_url="https://example.com/charger", currency="INR",
        price_minor=price_minor, stock="IN_STOCK",
        seller_rating=Decimal("4.6"), observed_at=at,
        evidence_sha256="e" * 64, event_id=new_event_id(),
    )


class EndToEndOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tracking.sqlite3"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def test_watch_to_source_history_to_alert_to_dashboard(self) -> None:
        watch_store = WatchStore(self.path)
        alerts = AlertStore(self.path)
        watch_id = watch_store.add_watch("USB Charger", "90", now=self.now)
        alerts.set_channel(watch_id, "EMAIL")

        # Offline history test fixtures: never exposed as real retailer quotes.
        for day in range(11, 0, -1):
            self.assertTrue(watch_store.prices.persist(
                source_quote(self.now - timedelta(days=day), 10000)))

        def mock_provider(query: str, *, limit: int) -> list[ProviderOffer]:
            self.assertEqual(query, "USB Charger")
            self.assertEqual(limit, 5)
            return [source_quote(self.now, 8000)]

        run = run_due_once(watch_store, now=self.now,
                           search=mock_provider, alerts=alerts)
        self.assertEqual(run[0]["status"], "OK")
        self.assertEqual(run[0]["inserted_observations"], 1)
        self.assertEqual(run[0]["queued_alerts"], 1)

        offer_id = watch_store.prices.list_offers()[0]["offer_id"]
        researched = research_offers(watch_store.prices, "USB Charger", "90",
                                     currency="INR", now=self.now)
        self.assertEqual(researched["matching_offers"], 1)
        self.assertEqual(researched["budget_candidates"], 1)
        self.assertEqual(researched["results"][0]["historical_deal"], "ALERT")
        history = daily_series(watch_store.prices, offer_id, now=self.now)
        self.assertEqual(history["observed_days"], 12)
        self.assertIn(price_trend(watch_store.prices, offer_id, now=self.now)["direction"],
                      {"LOWER", "HIGHER", "UNCHANGED", "UNKNOWN"})
        audit = audit_store(watch_store.prices, now=self.now)
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["observations"], 12)

        app = create_app(self.path, Path(self.temp.name) / "workspace.sqlite3")
        with TestClient(app) as client:
            result = client.get("/api/verified/research", params={
                "q": "USB Charger", "budget": "90", "currency": "INR",
            })
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()["research"]["matching_offers"], 1)
            intel = client.get(f"/api/verified/offers/{offer_id}/intelligence")
            self.assertEqual(intel.status_code, 200, intel.text)
            self.assertEqual(intel.json()["provider_requests"], 0)
            status = client.get("/api/verified/diagnostics")
            self.assertEqual(status.status_code, 200, status.text)
            self.assertEqual(status.json()["status"], "PASS")

        sent: list[tuple[str, str]] = []
        result = deliver_due(alerts, sender=lambda channel, message:
                             sent.append((channel, message)))
        self.assertEqual(result[0]["status"], "DELIVERED")
        self.assertEqual(sent[0][0], "EMAIL")
        self.assertEqual(alerts.list_deliveries()[0]["status"], "DELIVERED")

    def test_provider_cli_defaults_to_same_local_database_as_watch_tools(self) -> None:
        # Do not create any database or call a real API.
        with patch("price_engine.verified.cli.VerifiedPriceStore") as store:
            store.return_value.list_offers.return_value = []
            with patch("builtins.print"):
                status = provider_cli(["--list"])
            self.assertEqual(status, 0)
            store.assert_called_once_with("tracker.sqlite3")


if __name__ == "__main__":
    unittest.main()
