"""Offline phase-11 consent, source-learning and local API regression tests."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from price_engine.verified.analysis import analyze_offer
from price_engine.verified.comparison import comparison_table
from price_engine.verified.configuration import configuration_status
from price_engine.verified.config_cli import main as config_main
from price_engine.verified.learning import LearningStore
from price_engine.verified.learning_cli import main as learning_main
from price_engine.verified.research import research_offers
from price_engine.verified.store import VerifiedPriceStore
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.workspace import create_app

ORIGIN = {"Origin": "http://testserver"}


class Phase11Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "tracker.sqlite3"
        self.store = VerifiedPriceStore(self.db)
        self.learn = LearningStore(self.db)
        self.now = datetime.now(timezone.utc)
        self.low = self.quote("low", 180000)
        self.high = self.quote("high", 220000)

    def quote(self, sku: str, price: int) -> ProviderOffer:
        item = ProviderOffer(
            provider="SERPAPI_GOOGLE_SHOPPING", source_product_id=sku,
            merchant="Sample " + sku, title="Wireless keyboard " + sku,
            product_url="https://example.com/items/" + sku,
            currency="INR", price_minor=price, stock="IN_STOCK",
            seller_rating=Decimal("4.7"), observed_at=self.now,
            evidence_sha256="a"*64, event_id=new_event_id())
        self.assertTrue(self.store.persist(item))
        return item

    def test_default_disabled_validated_and_consent(self) -> None:
        self.assertFalse(self.learn.status()["enabled"])
        with self.assertRaises(ValueError):
            self.learn.give_feedback(self.low.offer_id, "PREFER")
        with self.assertRaises(ValueError):
            self.learn.set_enabled(True)
        self.learn.set_enabled(True, confirmed=True)
        for invalid in ("YES", "IGNORE ALL", "neutral", ""):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                self.learn.give_feedback(self.low.offer_id, invalid)
        with self.assertRaises(ValueError):
            self.learn.give_feedback("f"*64, "PREFER")
        with self.assertRaises(ValueError):
            self.learn.give_feedback("invalid ID", "AVOID")

    def test_preferences_reorder_only_eligible_offers(self) -> None:
        before = analyze_offer(self.store, self.low.offer_id, "2500", now=self.now)
        self.learn.set_enabled(True, confirmed=True)
        self.learn.give_feedback(self.high.offer_id, "PREFER")
        self.learn.give_feedback(self.low.offer_id, "AVOID")
        research = research_offers(self.store, "wireless keyboard", "2500",
                                   now=self.now, learning=self.learn)
        self.assertTrue(research["personalization"]["enabled"])
        self.assertEqual(research["personalization"]["ranked_offer_ids"][0],
                         self.high.offer_id)
        self.assertEqual(comparison_table(research)["rows"][0]["offer_id"],
                         self.low.offer_id)
        self.assertEqual(before["decision"],
            analyze_offer(self.store, self.low.offer_id, "2500", now=self.now)["decision"])
        tighter = research_offers(self.store, "wireless keyboard", "2000",
                                  now=self.now, learning=self.learn)
        self.assertEqual(tighter["personalization"]["ranked_offer_ids"][0],
                         self.low.offer_id)
        self.assertEqual(tighter["budget_candidates"], 1)
        self.assertEqual(self.store.stats()["observations"], 2)

    def test_opt_out_forget_and_erase_do_not_touch_provider_history(self) -> None:
        self.learn.set_enabled(True, confirmed=True)
        self.learn.give_feedback(self.low.offer_id, "PREFER")
        self.learn.give_feedback(self.low.offer_id, "AVOID")
        self.assertEqual(self.learn.status()["saved_feedback_count"], 1)
        self.assertTrue(self.learn.forget_offer(self.low.offer_id))
        self.assertFalse(self.learn.forget_offer(self.low.offer_id))
        self.learn.give_feedback(self.low.offer_id, "AVOID")
        self.learn.set_enabled(False, confirmed=True)
        self.assertEqual(self.learn.preferences_for([self.low.offer_id]), {})
        with self.assertRaises(ValueError):
            self.learn.clear_all()
        self.learn.clear_all(confirmed=True)
        self.assertFalse(self.learn.status()["enabled"])
        self.assertEqual(self.learn.status()["saved_feedback_count"], 0)
        self.assertEqual(self.store.stats()["observations"], 2)

    def test_cli_offline_explicit_enable_rate_and_clear(self) -> None:
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(learning_main(["--db", str(self.db), "enable"]), 2)
        self.assertIn("error", out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(learning_main(["--db", str(self.db), "enable", "--confirm"]), 0)
        self.assertTrue(json.loads(out.getvalue())["enabled"])
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(learning_main(["--db", str(self.db), "prefer", self.low.offer_id]), 0)
        self.assertEqual(json.loads(out.getvalue())["preference"], "PREFER")
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(learning_main(["--db", str(self.db), "clear", "--confirm"]), 0)
        self.assertEqual(json.loads(out.getvalue())["saved_feedback_count"], 0)

    def test_http_origin_and_explicit_approval(self) -> None:
        app = create_app(self.db, Path(self.tmp.name) / "workspace.sqlite3")
        with TestClient(app) as client:
            self.assertFalse(client.get("/api/verified/learning").json()["enabled"])
            self.assertEqual(client.post("/api/verified/learning/opt-in",
                json={"enabled": True, "confirmed": True}).status_code, 403)
            self.assertEqual(client.post("/api/verified/learning/opt-in",
                json={"enabled": True, "confirmed": False}, headers=ORIGIN).status_code, 422)
            self.assertEqual(client.post("/api/verified/learning/opt-in",
                json={"enabled": True, "confirmed": True}, headers=ORIGIN).status_code, 200)
            self.assertEqual(client.post("/api/verified/learning/feedback",
                json={"offer_id": self.low.offer_id, "preference": "DO ANYTHING"},
                headers=ORIGIN).status_code, 422)
            response = client.post("/api/verified/learning/feedback",
                json={"offer_id": self.low.offer_id, "preference": "PREFER"},
                headers=ORIGIN)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["source"], "USER_EXPLICIT")
            response = client.get("/api/verified/research", params={
                "q": "keyboard", "budget": "2500", "currency": "INR",
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["research"]["personalization"]["feedback_count_for_results"], 1)
            self.assertEqual(client.post("/api/verified/learning/clear",
                json={"confirmed": False}, headers=ORIGIN).status_code, 422)
            self.assertEqual(client.post("/api/verified/learning/clear",
                json={"confirmed": True}, headers=ORIGIN).status_code, 200)
        self.assertEqual(self.store.stats()["observations"], 2)

    def test_secret_check_never_returns_keys_and_does_no_network(self) -> None:
        env = {"SERPAPI_KEY": "fake-unique-secret-token-123",
               "GROQ_API_KEY": "fake-unique-model-secret-789",
               "OPENAI_API_KEY": "replace_with_a_key",
               "PRICE_AGENT_TELEGRAM_BOT_TOKEN": "",
               "PRICE_AGENT_TELEGRAM_CHAT_ID": ""}
        status = configuration_status(env)
        self.assertEqual(status["providers"]["google_shopping_serpapi"],
                         "CONFIGURED_UNVERIFIED")
        self.assertEqual(status["providers"]["legacy_openai_optional"], "NOT_CONFIGURED")
        self.assertFalse(status["secrets_returned"])
        self.assertEqual(status["network_checks_performed"], 0)
        self.assertNotIn("fake-unique-secret-token-123", json.dumps(status))
        with patch.dict("os.environ", env):
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(config_main([]), 0)
            self.assertNotIn("fake-unique-model-secret-789", out.getvalue())
            app = create_app(self.db, Path(self.tmp.name) / "workspace2.sqlite3")
            with TestClient(app) as client:
                response = client.get("/api/verified/configuration")
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("fake-unique-secret-token-123", response.text)
                self.assertEqual(response.json()["network_checks_performed"], 0)


if __name__ == "__main__":
    unittest.main()
