"""Offline/demo launch, with a private synthetic-only database and no API keys."""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from .offline_demo import DemoStore
from .storage import PriceStore
from .workspace import create_app

ROOT = Path(__file__).resolve().parents[2]


def app_for_demo(data_dir: str | Path):
    location = Path(data_dir).expanduser().resolve()
    location.mkdir(parents=True, exist_ok=True)
    # Three separate DBs: legacy read-only history, uploaded workspace,
    # and DEMO_FIXTURE-only simulation. Never open the user's real tracker.
    legacy = location / "legacy_demo.sqlite3"
    workspace = location / "workspace_demo.sqlite3"
    synthetic = location / "synthetic_demo.sqlite3"
    PriceStore(legacy, ROOT / "backend" / "migrations" / "001_initial.sql").close()
    return create_app(legacy, workspace, offline_only=True, demo_db=synthetic)


def run_smoke() -> int:
    from fastapi.testclient import TestClient
    with tempfile.TemporaryDirectory() as temp:
        app = app_for_demo(temp)
        with TestClient(app) as client:
            base = client.get("/api/demo/status").json()
            assert base["mode"] == "DEMO_FIXTURE" and base["offline_only"]
            products = client.get("/api/demo/search", params={
                "q": "headphones", "budget": "4000"}).json()["offers"]
            assert products and all(p["provenance"] == "DEMO_FIXTURE" for p in products)
            offer = products[0]
            assert client.get(f"/api/demo/history/{offer['offer_id']}").status_code == 200
            assert client.get(f"/api/demo/analysis/{offer['offer_id']}",
                              params={"budget": "4000"}).status_code == 200
            assert client.get(f"/api/demo/explain/{offer['offer_id']}",
                              params={"budget": "4000"}).json()["ai_model_called"] is False
            headers = {"Origin": "http://testserver"}
            assert client.post("/api/demo/learning",
                json={"enabled": True, "confirmed": True}, headers=headers).status_code == 200
            assert client.post("/api/demo/feedback",
                json={"offer_id": offer["offer_id"], "preference": "PREFER"},
                headers=headers).status_code == 200
            saved = client.post("/api/demo/watch", json={
                "query": "headphones", "budget": "4000",
                "channel": "SIMULATED_EMAIL", "confirmed": True
            }, headers=headers)
            assert saved.status_code == 200, saved.text
            poll = client.post("/api/demo/poll", json={"confirmed": True}, headers=headers)
            assert poll.status_code == 200, poll.text
            dispatch = client.post("/api/demo/dispatch",
                                   json={"confirmed": True}, headers=headers)
            assert dispatch.status_code == 200, dispatch.text
            assert dispatch.json()["real_messages_sent"] == 0
            assert client.get("/api/demo/diagnostics").json()["status"] == "PASS"
            assert client.get("/api/demo/config").json()["network_requests"] == 0
            assert client.get("/api/demo/catalog").json()["source"] == "DEMO_FIXTURE"
            assert client.get("/verified", follow_redirects=False).status_code == 307
            assert client.post("/api/verified/search", headers=headers, json={
                "query": "headphones", "budget": "4000"
            }).status_code == 409
    print("PASS: isolated offline demo (search, price history, analysis,")
    print("explanations, local learning, watches, simulated alerts, API gate and audit)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Price Agent isolated offline demo; no network, real prices or API keys")
    parser.add_argument("command", nargs="?", choices=("serve", "smoke"), default="serve")
    parser.add_argument("--data-dir", default=str(ROOT / ".price-agent-demo"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Unauthenticated offline demo is restricted to loopback")
    if args.command == "smoke":
        return run_smoke()
    import uvicorn
    app = app_for_demo(args.data_dir)
    print("OFFLINE DEMO: fictional prices, local simulated alerts, no external provider calls.")
    print(f"Open http://127.0.0.1:{args.port}/demo")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
