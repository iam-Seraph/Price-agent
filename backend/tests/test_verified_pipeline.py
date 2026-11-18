"""Offline integration tests for real-only provider ingestion and SQLite history."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from price_engine.verified.analysis import analyze_offer
from price_engine.verified.cli import main as cli_main
from price_engine.verified.money import minor_units, provider_price
from price_engine.verified.provider import ProviderUnavailable, parse_shopping_results, search_serpapi
from price_engine.verified.store import VerifiedPriceStore
from price_engine.verified.types import ProviderOffer, new_event_id, safe_evidence_url


def make_quote(*, when: datetime, cents: int = 10000,
               stock: str = "IN_STOCK", rating: Decimal | None = Decimal("4.7")) -> ProviderOffer:
    return ProviderOffer(
        provider="SERPAPI_GOOGLE_SHOPPING", source_product_id="sku-42",
        merchant="Example Merchant", title="Example Headphones",
        product_url="https://store.example.com/products/headphones",
        currency="INR", price_minor=cents, stock=stock, seller_rating=rating,
        observed_at=when, evidence_sha256="a" * 64, event_id=new_event_id(),
    )


class MoneyValidationTests(unittest.TestCase):
    def test_integer_minor_units(self) -> None:
        self.assertEqual(minor_units("1,23,456.70", "INR"), 12345670)
        self.assertEqual(provider_price("₹1,250.00", 1250.0), (125000, "INR"))
        self.assertEqual(provider_price("$19.99", 19.99), (1999, "USD"))

    def test_reject_unsafe_price_inputs(self) -> None:
        for value in ("-10", "NaN", "Infinity", "12.345", "1e9", "₹500", "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                minor_units(value, "INR")
        with self.assertRaises(ValueError):
            provider_price("₹120.00", 100)

    def test_reject_internal_urls(self) -> None:
        for url in ("http://example.com/item", "https://127.0.0.1/item",
                    "https://localhost/item", "https://user:password@example.com/item"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                safe_evidence_url(url)


class ProviderIntegrationTests(unittest.TestCase):
    def test_http_adapter_returns_real_source_attributed_quote(self) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "serpapi.com")
            self.assertEqual(request.url.params["engine"], "google_shopping")
            return httpx.Response(200, json={"shopping_results": [{
                "title": "Headphones X", "source": "Retailer A",
                "product_id": "123", "link": "https://shop.example.com/p/123",
                "price": "₹2,499.00", "extracted_price": 2499,
            }]})
        result = search_serpapi("headphones", api_key="fake-test-key",
                                transport=httpx.MockTransport(respond))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].price_minor, 249900)
        self.assertIsNone(result[0].seller_rating)
        self.assertEqual(result[0].stock, "UNKNOWN")

    def test_error_does_not_fall_back_to_fake_data(self) -> None:
        def unavailable(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)
        with self.assertRaises(ProviderUnavailable):
            search_serpapi("headphones", api_key="fake-test-key",
                           transport=httpx.MockTransport(unavailable))
        self.assertEqual(parse_shopping_results({"shopping_results": []},
                         datetime.now(timezone.utc)), [])

    def test_source_and_currency_are_required(self) -> None:
        now = datetime.now(timezone.utc)
        rows = {"shopping_results": [
            {"title": "A", "source": "Store", "product_id": "a",
             "link": "https://shop.example.com/a", "price": "99.00"},
            {"title": "B", "source": "Store", "product_id": "b",
             "link": "https://shop.example.com/b", "price": "₹99.00"},
        ]}
        result = parse_shopping_results(rows, now)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source_product_id, "b")


class SQLiteAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = VerifiedPriceStore(Path(self.tmp.name) / "history.sqlite3")
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_consecutive_history_days_can_verify_deal(self) -> None:
        for n in range(11, 0, -1):
            quote = make_quote(when=self.now-timedelta(days=n), cents=10000)
            self.assertTrue(self.store.persist(quote))
        lowered = make_quote(when=self.now, cents=8000)
        self.store.persist(lowered)
        result = analyze_offer(self.store, lowered.offer_id, "90", now=self.now)
        self.assertEqual(result["decision"], "ALERT")
        self.assertEqual(result["all_time_low_minor"], 8000)
        self.assertGreaterEqual(result["unique_days_30d"], 10)
        self.assertEqual(result["provenance"], "PROVIDER_REPORTED")

    def test_missing_seller_or_stock_evidence_fails_closed(self) -> None:
        quote = make_quote(when=self.now, rating=None, stock="UNKNOWN")
        self.store.persist(quote)
        result = analyze_offer(self.store, quote.offer_id, "110", now=self.now)
        self.assertEqual(result["decision"], "NO_ALERT")
        self.assertFalse(result["checks"]["seller_evidence"])
        self.assertFalse(result["checks"]["stock_confirmed"])
        self.assertFalse(result["checks"]["history_depth"])

    def test_idempotency_and_conflicting_replay(self) -> None:
        quote = make_quote(when=self.now)
        self.assertTrue(self.store.persist(quote))
        self.assertFalse(self.store.persist(quote))
        with self.assertRaises(ValueError):
            self.store.persist(replace(quote, price_minor=9999))
        self.assertEqual(len(self.store.list_offers()), 1)

    def test_stale_data_cannot_raise_alert(self) -> None:
        for n in range(12, 0, -1):
            self.store.persist(make_quote(when=self.now-timedelta(days=n), cents=10000))
        q = make_quote(when=self.now-timedelta(days=2), cents=8000)
        self.store.persist(q)
        report = analyze_offer(self.store, q.offer_id, "90", now=self.now)
        self.assertEqual(report["decision"], "NO_ALERT")
        self.assertFalse(report["checks"]["recent_evidence"])

    def test_stored_report_cli_needs_no_network(self) -> None:
        quote = make_quote(when=self.now)
        self.store.persist(quote)
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = cli_main(["--db", str(self.store.path), "--offer-id", quote.offer_id,
                             "--budget", "110", "--currency", "INR"])
        self.assertEqual(code, 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result["analyses"][0]["offer_id"], quote.offer_id)
        self.assertFalse(result["live_provider_called"])


if __name__ == "__main__":
    unittest.main()
