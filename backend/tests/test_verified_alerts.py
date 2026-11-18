"""Outbox and opt-in sender regression tests; all outbound transports are mocked."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from price_engine.verified.alert_store import AlertStore
from price_engine.verified.delivery import deliver_due
from price_engine.verified.notifier import AlertConfigurationError
from price_engine.verified.types import ProviderOffer, new_event_id


def make_quote(now: datetime, amount: int) -> ProviderOffer:
    return ProviderOffer(
        provider="SERPAPI_GOOGLE_SHOPPING", source_product_id="sku-100",
        merchant="Sample Test Shop", title="USB Type C Charger",
        product_url="https://example.com/products/usb-charger",
        currency="INR", price_minor=amount, stock="IN_STOCK",
        seller_rating=Decimal("4.7"), observed_at=now,
        evidence_sha256="f" * 64, event_id=new_event_id())


class AlertOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tracker.sqlite3"
        self.alerts = AlertStore(self.db)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.watch_id = self.alerts.watches.add_watch(
            "USB Type C charger", "90", now=self.now)
        for day in range(11, 0, -1):
            self.alerts.watches.prices.persist(make_quote(
                self.now - timedelta(days=day), 10000))
        self.current = make_quote(self.now, 8000)
        self.alerts.watches.prices.persist(self.current)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_no_alert_without_explicit_channel_opt_in(self) -> None:
        self.assertEqual(self.alerts.enqueue_if_qualified(
            self.watch_id, self.current.offer_id), 0)
        self.assertEqual(self.alerts.list_deliveries(), [])

    def test_dedup_and_successful_mock_delivery(self) -> None:
        self.alerts.set_channel(self.watch_id, "EMAIL")
        self.assertEqual(self.alerts.enqueue_if_qualified(
            self.watch_id, self.current.offer_id), 1)
        self.assertEqual(self.alerts.enqueue_if_qualified(
            self.watch_id, self.current.offer_id), 0)
        emitted = []
        results = deliver_due(self.alerts,
            sender=lambda channel, message: emitted.append((channel, message)))
        self.assertEqual(results[0]["status"], "DELIVERED")
        self.assertEqual(emitted[0][0], "EMAIL")
        self.assertIn("Provider-reported price", emitted[0][1])
        self.assertEqual(self.alerts.list_deliveries()[0]["status"], "DELIVERED")

    def test_missing_transport_credentials_fails_closed(self) -> None:
        self.alerts.set_channel(self.watch_id, "TELEGRAM")
        self.alerts.enqueue_if_qualified(self.watch_id, self.current.offer_id)
        def missing(channel: str, message: str) -> None:
            raise AlertConfigurationError("Credentials not configured")
        results = deliver_due(self.alerts, sender=missing)
        self.assertEqual(results[0]["status"], "FAILED")
        self.assertEqual(results[0]["error_code"], "CHANNEL_NOT_CONFIGURED")

    def test_queue_is_released_and_capped_for_retries(self) -> None:
        self.alerts.set_channel(self.watch_id, "EMAIL")
        self.alerts.enqueue_if_qualified(self.watch_id, self.current.offer_id)
        first = self.alerts.claim_deliveries(now=self.now)
        self.assertEqual(len(first), 1)
        self.assertEqual(self.alerts.claim_deliveries(now=self.now), [])
        state = self.alerts.complete_delivery(first[0], success=False,
            retryable=True, error_code="TEST_NETWORK", now=self.now)
        self.assertEqual(state, "QUEUED")
        self.assertEqual(self.alerts.claim_deliveries(now=self.now), [])
        second = self.alerts.claim_deliveries(now=self.now+timedelta(seconds=61))
        self.assertEqual(len(second), 1)
        self.assertEqual(self.alerts.complete_delivery(
            second[0], success=True, now=self.now+timedelta(seconds=61)), "DELIVERED")

    def test_disable_channel_cancels_pending_delivery(self) -> None:
        self.alerts.set_channel(self.watch_id, "EMAIL")
        self.alerts.enqueue_if_qualified(self.watch_id, self.current.offer_id)
        self.alerts.set_channel(self.watch_id, "EMAIL", enabled=False)
        self.assertEqual(self.alerts.list_deliveries()[0]["status"], "FAILED")
        self.assertEqual(self.alerts.claim_deliveries(), [])


if __name__ == "__main__":
    unittest.main()
