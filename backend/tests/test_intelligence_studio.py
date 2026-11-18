"""Smoke checks for the isolated, fictional Intelligence Studio route."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fastapi.testclient import TestClient
from price_engine.workspace import create_app


class IntelligenceStudioTests(TestCase):
    def test_page_and_local_assets(self) -> None:
        with TemporaryDirectory() as tmp:
            history = Path(tmp) / "read-only.sqlite3"
            workspace = Path(tmp) / "workspace.sqlite3"
            with TestClient(create_app(history, workspace)) as client:
                page = client.get("/intelligence")
                self.assertEqual(page.status_code, 200)
                self.assertIn("Natural language product search", page.text)
                self.assertIn("SIMULATION MODE", page.text)
                self.assertIn("no emails are sent or uploaded", page.text)
                self.assertEqual(page.headers.get("cache-control"), "no-store")
                self.assertIn("script-src 'self'", page.headers.get("content-security-policy", ""))
                for asset in ["intelligence.js", "intelligence.worker.js", "intelligence.css", "intelligence-favicon.svg"]:
                    result = client.get("/static/" + asset)
                    self.assertEqual(result.status_code, 200, asset)
                    self.assertGreater(len(result.content), 100, asset)

    def test_existing_routes_still_available(self) -> None:
        with TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.sqlite3"
            workspace = Path(tmp) / "workspace.sqlite3"
            with TestClient(create_app(history, workspace)) as client:
                for page in ["/", "/catalog", "/workspace"]:
                    result = client.get(page)
                    self.assertEqual(result.status_code, 200)
                    self.assertIn("/intelligence", result.text)
