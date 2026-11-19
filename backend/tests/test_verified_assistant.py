"""Restricted natural-language shopping commands: no unconfirmed writes."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from price_engine.verified.assistant import execute_command, plan_command
from price_engine.verified.commands import parse_shopping_intent
from price_engine.verified.store import VerifiedPriceStore
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.verified.watch_store import WatchStore
from price_engine.workspace import create_app


class NaturalLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "history.sqlite3"
        self.workspace = Path(self.tmp.name) / "workspace.sqlite3"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_supported_commands_and_exact_amounts(self) -> None:
        intent = parse_shopping_intent("notify me when laptop drops below ₹60,000")
        self.assertEqual(intent.action, "CREATE_WATCH")
        self.assertEqual(intent.budget_minor, 6000000)
        self.assertTrue(intent.requires_confirmation)
        self.assertEqual(intent.currency, "INR")
        comparison = parse_shopping_intent("compare wireless keyboard under $50.00")
        self.assertEqual(comparison.action, "COMPARE_STORED")
        self.assertEqual(comparison.budget_minor, 5000)
        self.assertFalse(comparison.requires_confirmation)

    def test_reject_ambiguous_and_unapproved_commands(self) -> None:
        for command in ("delete all files", "watch headset below ₹50/month",
                        "watch headset below ₹1,2,3",
                        "notify me when headphones drop below ₹500",
                        "watch item below €100", "watch item\nbelow ₹500"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                parse_shopping_intent(command)

    def test_watch_requires_confirmation_and_is_idempotent(self) -> None:
        command = "watch headset below ₹2500"
        planned = plan_command(command)
        self.assertTrue(planned["needs_explicit_confirmation"])
        unconfirmed = execute_command(self.db, command)
        self.assertEqual(unconfirmed["status"], "CONFIRMATION_REQUIRED")
        self.assertEqual(WatchStore(self.db).list_watches(), [])
        first = execute_command(self.db, command, confirmed=True)
        second = execute_command(self.db, command, confirmed=True)
        self.assertEqual(first["status"], "WATCH_SAVED")
        self.assertEqual(first["watch_id"], second["watch_id"])
        self.assertFalse(first["polling_started"])
        self.assertFalse(first["notification_configured"])
        self.assertEqual(len(WatchStore(self.db).list_watches()), 1)

    def test_comparison_only_reads_stored_provider_evidence(self) -> None:
        store = VerifiedPriceStore(self.db)
        quote = ProviderOffer(
            provider="SERPAPI_GOOGLE_SHOPPING", source_product_id="headset-1",
            merchant="Example Shop", title="Wireless Headset",
            product_url="https://example.com/headset-1", currency="INR",
            price_minor=199900, stock="UNKNOWN", seller_rating=None,
            observed_at=datetime.now(timezone.utc),
            evidence_sha256="b"*64, event_id=new_event_id(),
        )
        store.persist(quote)
        result = execute_command(self.db, "compare wireless headset under ₹2500")
        self.assertEqual(result["status"], "RESEARCH_COMPLETED")
        self.assertEqual(result["research"]["matching_offers"], 1)
        self.assertEqual(WatchStore(self.db).list_watches(), [])

    def test_http_planning_and_confirmation(self) -> None:
        with TestClient(create_app(self.db, self.workspace)) as client:
            command = "watch keyboard below ₹3500"
            no_origin = client.post("/api/verified/assistant/plan",
                                    json={"command": command})
            self.assertEqual(no_origin.status_code, 403)
            plan = client.post("/api/verified/assistant/plan",
                               json={"command": command},
                               headers={"Origin": "http://testserver"})
            self.assertEqual(plan.status_code, 200)
            self.assertTrue(plan.json()["needs_explicit_confirmation"])
            unconfirmed = client.post("/api/verified/assistant/execute",
                json={"command": command, "confirmed": False},
                headers={"Origin": "http://testserver"})
            self.assertEqual(unconfirmed.json()["status"], "CONFIRMATION_REQUIRED")
            self.assertEqual(client.get("/api/verified/watches").json()["watches"], [])
            approved = client.post("/api/verified/assistant/execute",
                json={"command": command, "confirmed": True},
                headers={"Origin": "http://testserver"})
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["status"], "WATCH_SAVED")
            self.assertEqual(len(client.get("/api/verified/watches").json()["watches"]), 1)


if __name__ == "__main__":
    unittest.main()
