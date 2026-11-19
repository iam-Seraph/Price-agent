"""Phase 10 integrity, security headers, and deployment-boundary regressions."""
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

from price_engine.verified.audit import audit_store
from price_engine.verified.audit_cli import main as audit_main
from price_engine.verified.store import VerifiedPriceStore
from price_engine.verified.types import ProviderOffer, new_event_id
from price_engine.workspace import create_app


class ReleaseAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "verified.sqlite3"
        self.store = VerifiedPriceStore(self.db_path)
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    def quote(self) -> ProviderOffer:
        row = ProviderOffer(
            provider="SERPAPI_GOOGLE_SHOPPING",
            source_product_id="readiness-sku",
            merchant="Example Retailer",
            title="Source-backed Headphones",
            product_url="https://retailer.example.com/p/headphones",
            currency="INR", price_minor=250000,
            stock="IN_STOCK", seller_rating=Decimal("4.5"),
            observed_at=self.now, evidence_sha256="c"*64,
            event_id=new_event_id(),
        )
        self.assertTrue(self.store.persist(row))
        return row

    def test_empty_database_has_valid_structure_not_verified_prices(self) -> None:
        result = audit_store(self.store, now=self.now)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["offers"], 0)
        self.assertEqual(result["observations"], 0)
        self.assertFalse(result["multi_user_authorization_enabled"])
        self.assertEqual(result["database_scope"], "SINGLE_OPERATOR")
        self.assertEqual(result["provider_network_requests"], 0)

    def test_populated_database_audit_and_readonly_cli(self) -> None:
        self.quote()
        before = self.store.stats()["observations"]
        result = audit_store(self.store, now=self.now)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["offers"], 1)
        self.assertEqual(result["observations"], 1)
        output = io.StringIO()
        with redirect_stdout(output):
            code = audit_main(["--db", str(self.db_path)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["provider_network_requests"], 0)
        self.assertEqual(self.store.stats()["observations"], before)

    def test_suspicious_future_observation_is_reported(self) -> None:
        quote = self.quote()
        future = (self.now+timedelta(days=2)).isoformat(
            timespec="microseconds").replace("+00:00", "Z")
        # Raw SQL simulates altered data; ordinary ingestion rejects future observations.
        with self.store.connect() as db:
            with db:
                db.execute("""
                    INSERT INTO verified_offer_observations
                    (event_id,offer_id,observed_at,price_minor,stock,seller_rating,
                     evidence_sha256,provenance,ingested_at)
                    SELECT ?,offer_id,?,price_minor,stock,seller_rating,
                           evidence_sha256,provenance,ingested_at
                    FROM verified_offer_observations WHERE offer_id=? LIMIT 1
                """, ("f"*32, future, quote.offer_id))
        result = audit_store(self.store, now=self.now)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["no_impossible_future_observations"])
        self.assertEqual(result["impossible_future_observations"], 1)

    def test_bad_or_missing_database_does_not_claim_readiness(self) -> None:
        path = Path(self.temp.name) / "missing.sqlite3"
        output = io.StringIO()
        with redirect_stdout(output):
            code = audit_main(["--db", str(path)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "ERROR")
        with self.assertRaises(ValueError):
            audit_store(self.store, now=datetime(2026, 1, 1))

    def test_http_diagnostics_and_verified_security_headers(self) -> None:
        self.quote()
        app = create_app(self.db_path, Path(self.temp.name) / "workspace.sqlite3")
        with TestClient(app) as client:
            response = client.get("/api/verified/diagnostics")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["status"], "PASS")
            self.assertFalse(body["multi_user_authorization_enabled"])
            self.assertEqual(response.headers.get("cache-control"), "no-store")
            self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
            self.assertEqual(response.headers.get("x-frame-options"), "DENY")
            self.assertNotIn("api_key", json.dumps(body).lower())
            page = client.get("/verified")
            self.assertEqual(page.status_code, 200, page.text)
            self.assertIn("default-src 'self'", page.headers.get("content-security-policy", ""))
            self.assertEqual(page.headers.get("referrer-policy"), "no-referrer")
            forbidden = client.post("/api/verified/assistant/plan",
                                    json={"command": "compare headset under ₹3000"})
            self.assertEqual(forbidden.status_code, 403)


if __name__ == "__main__":
    unittest.main()
