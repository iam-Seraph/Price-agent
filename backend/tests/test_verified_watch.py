"""Offline watchlist and single-runner lease regression tests."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from price_engine.verified.monitor import run_due_once
from price_engine.verified.provider import ProviderUnavailable
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.verified.watch_cli import main as watch_main
from price_engine.verified.watch_store import WatchStore
from price_engine.workspace import create_app


def quote(when: datetime) -> ProviderOffer:
    return ProviderOffer(
        provider="SERPAPI_GOOGLE_SHOPPING",
        source_product_id="source-01", merchant="Test Retailer",
        title="USB Keyboard", product_url="https://example.com/keyboard",
        currency="INR", price_minor=299900, stock="IN_STOCK",
        seller_rating=Decimal("4.3"), observed_at=when,
        evidence_sha256="d" * 64, event_id=new_event_id())


class WatchStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tracked.sqlite3"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.store = WatchStore(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_validated_watch_inputs(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_watch("a", "100")
        with self.assertRaises(ValueError):
            self.store.add_watch("keyboard", "100", interval_minutes=1)
        watch_id = self.store.add_watch("USB keyboard", "2500", now=self.now)
        self.assertEqual(len(watch_id), 32)
        self.assertEqual(self.store.list_watches()[0]["budget_minor"], 250000)
        self.assertTrue(self.store.disable_watch(watch_id))
        self.assertFalse(self.store.disable_watch(watch_id))

    def test_only_one_worker_can_claim_a_due_watch(self) -> None:
        self.store.add_watch("USB keyboard", "3000", now=self.now)
        first = self.store.claim_due(now=self.now)
        self.assertEqual(len(first), 1)
        self.assertEqual(self.store.claim_due(now=self.now), [])
        self.store.complete_claim(first[0], status="NO_MATCHES",
                                  offers_inspected=0, inserted_observations=0,
                                  now=self.now)
        self.assertEqual(self.store.claim_due(now=self.now), [])
        due = self.store.claim_due(now=self.now+timedelta(hours=1))
        self.assertEqual(len(due), 1)
        self.assertEqual(len(self.store.recent_runs()), 1)

    def test_provider_failures_write_no_invented_prices(self) -> None:
        self.store.add_watch("USB keyboard", "3500", now=self.now)
        def fail(query: str, *, limit: int):
            raise ProviderUnavailable("No live response")
        records = run_due_once(self.store, now=self.now, search=fail)
        self.assertEqual(records[0]["status"], "PROVIDER_UNAVAILABLE")
        self.assertEqual(self.store.prices.list_offers(), [])
        self.assertEqual(self.store.recent_runs()[0]["inserted_observations"], 0)
        self.assertEqual(self.store.claim_due(now=self.now+timedelta(minutes=30)), [])

    def test_persisted_provider_quotes_are_only_monitor_records(self) -> None:
        self.store.add_watch("USB keyboard", "3500", now=self.now)
        def search(query: str, *, limit: int):
            self.assertEqual(query, "USB keyboard")
            return [quote(self.now)]
        records = run_due_once(self.store, now=self.now, search=search)
        self.assertEqual(records[0]["inserted_observations"], 1)
        self.assertEqual(records[0]["status"], "OK")
        listed = self.store.prices.list_offers()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["latest_price_minor"], 299900)

    def test_continuous_worker_keeps_alert_store_enabled(self) -> None:
        # Stop at the first iteration: no network access or infinite loop.
        log = io.StringIO()
        with patch("price_engine.verified.watch_cli.run_due_once",
                   side_effect=KeyboardInterrupt) as run:
            with redirect_stdout(log):
                status = watch_main(["--db", str(self.db), "run",
                                     "--continuous", "--sleep-seconds", "15"])
        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 1)
        self.assertIn("alerts", run.call_args.kwargs)
        from price_engine.verified.alert_store import AlertStore
        self.assertIsInstance(run.call_args.kwargs["alerts"], AlertStore)

    def test_cli_and_readonly_watch_api(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(watch_main(["--db", str(self.db), "add",
                                        "USB keyboard", "--budget", "3200"]), 0)
        self.assertTrue(json.loads(output.getvalue())["saved"])
        app = create_app(self.db, Path(self.tmp.name)/"workspace.sqlite3")
        with TestClient(app) as client:
            response = client.get("/api/verified/watches")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.json()["watches"]), 1)
            audit = client.get("/api/verified/watch-runs")
            self.assertEqual(audit.status_code, 200)
            self.assertEqual(audit.json()["runs"], [])


if __name__ == "__main__":
    unittest.main()
