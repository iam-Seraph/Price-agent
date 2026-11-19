"""Offline regression tests for bounded source-attributed historical intelligence."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from price_engine.verified.intelligence import (
    daily_series, detect_price_anomaly, price_trend,
)
from price_engine.verified.intelligence_cli import main as cli_main
from price_engine.verified.quality import evidence_quality
from price_engine.verified.store import VerifiedPriceStore
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.workspace import create_app


class HistoricalIntelligenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "verified.sqlite3"
        self.store = VerifiedPriceStore(self.path)
        self.clock = datetime.now(timezone.utc).replace(microsecond=0)

    def record(self, days: int, price: int, *, stock: str = "IN_STOCK",
               rating: Decimal | None = Decimal("4.7"), hours: int = 0) -> ProviderOffer:
        offer = ProviderOffer(
            provider="SERPAPI_GOOGLE_SHOPPING", source_product_id="sku-intel",
            merchant="Recorded Shop", title="Source Headphones",
            product_url="https://shop.example.com/source-headphones",
            currency="INR", price_minor=price, stock=stock,
            seller_rating=rating,
            observed_at=self.clock-timedelta(days=days, hours=hours),
            evidence_sha256="b"*64, event_id=new_event_id(),
        )
        self.assertTrue(self.store.persist(offer))
        return offer

    def test_daily_history_has_no_missing_days_or_out_of_stock_low(self) -> None:
        offer = self.record(5, 20000)
        self.record(3, 18000)
        self.record(3, 12000)
        self.record(1, 1, stock="OUT_OF_STOCK")
        report = daily_series(self.store, offer.offer_id, now=self.clock)
        self.assertEqual(report["observed_days"], 2)
        self.assertEqual(report["records_discarded"], 1)
        self.assertEqual(report["series"][-1]["daily_median_minor"], 12000)
        self.assertEqual(report["series"][-1]["observations"], 2)

    def test_detects_sharp_drop_only_with_ten_prior_days(self) -> None:
        offer = self.record(12, 20000)
        for day in range(11, 0, -1):
            self.record(day, 20000)
        self.record(0, 9000)
        report = detect_price_anomaly(self.store, offer.offer_id, now=self.clock)
        self.assertTrue(report["is_anomaly"])
        self.assertEqual(report["status"], "SHARP_PRICE_DROP")
        self.assertEqual(report["baseline_minor"], 20000)

    def test_out_of_stock_latest_cannot_create_anomaly(self) -> None:
        offer = self.record(11, 20000)
        for day in range(10, 0, -1):
            self.record(day, 20000)
        self.record(0, 1, stock="OUT_OF_STOCK")
        report = detect_price_anomaly(self.store, offer.offer_id, now=self.clock)
        self.assertFalse(report["is_anomaly"])
        self.assertEqual(report["status"], "UNVERIFIED_CURRENT_PRICE")
        self.assertIsNone(report["current_price_minor"])

    def test_sparse_data_fails_closed(self) -> None:
        offer = self.record(0, 12000, rating=None, stock="UNKNOWN")
        result = detect_price_anomaly(self.store, offer.offer_id, now=self.clock)
        self.assertEqual(result["status"], "UNVERIFIED_CURRENT_PRICE")
        score = evidence_quality(self.store, offer.offer_id, now=self.clock)
        self.assertFalse(score["checks"]["history_depth"])
        self.assertFalse(score["checks"]["known_stock"])
        self.assertIsNone(score["merchant_reliability_score"])
        self.assertLess(score["evidence_completeness_score"], 100)
        self.assertEqual(price_trend(self.store, offer.offer_id, now=self.clock)["direction"], "UNKNOWN")

    def test_observed_trend_without_forecasting(self) -> None:
        offer = self.record(13, 20000)
        for day in range(12, -1, -1):
            self.record(day, 20000 if day >= 7 else 16000)
        trend = price_trend(self.store, offer.offer_id, now=self.clock)
        self.assertEqual(trend["status"], "OBSERVED")
        self.assertEqual(trend["direction"], "LOWER")
        self.assertEqual(trend["older_median_minor"], 20000)
        self.assertEqual(trend["recent_median_minor"], 16000)

    def test_as_of_window_rejects_future_and_invalid_clocks(self) -> None:
        offer = self.record(5, 10000)
        self.record(0, 20000)
        earlier = self.clock-timedelta(days=2)
        result = daily_series(self.store, offer.offer_id, now=earlier, days=10)
        self.assertEqual(result["observed_days"], 1)
        with self.assertRaises(ValueError):
            daily_series(self.store, offer.offer_id, now=datetime(2026,1,1))
        with self.assertRaises(ValueError):
            daily_series(self.store, offer.offer_id, days=500)
        with self.assertRaises(ValueError):
            daily_series(self.store, "z"*64, now=self.clock)

    def test_read_only_http_and_cli(self) -> None:
        offer = self.record(0, 10000)
        original = self.store.stats()["observations"]
        with TestClient(create_app(self.path, Path(self.temp.name)/"workspace.sqlite3")) as client:
            endpoint = "/api/verified/offers/" + offer.offer_id + "/intelligence"
            response = client.get(endpoint)
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["series"]["observed_days"], 1)
            self.assertEqual(body["anomaly"]["status"], "INSUFFICIENT_PRIOR_DAYS")
            self.assertIn("evidence", body)
            self.assertEqual(client.get(endpoint, params={"days": 400}).status_code, 422)
            self.assertEqual(client.get("/api/verified/offers/" + "0"*64 + "/intelligence").status_code, 404)
        output = io.StringIO()
        with redirect_stdout(output):
            status = cli_main([offer.offer_id, "--db", str(self.path)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["network_requests"], 0)
        self.assertEqual(self.store.stats()["observations"], original)


if __name__ == "__main__":
    unittest.main()
