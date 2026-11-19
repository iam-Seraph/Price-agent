"""HTTP surfaces for the isolated simulated Price Agent.

These endpoints NEVER call web providers or real notification transports.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .offline_demo import DemoStore

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


class DemoWatchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    budget: str = Field(min_length=1, max_length=30)
    channel: Literal["SIMULATED_EMAIL", "SIMULATED_TELEGRAM"] = "SIMULATED_EMAIL"
    confirmed: bool = False


class Confirmation(BaseModel):
    confirmed: bool = False


class DemoLearningToggle(Confirmation):
    enabled: bool


class DemoFeedback(BaseModel):
    offer_id: str = Field(min_length=32, max_length=32)
    preference: Literal["PREFER", "AVOID"]


class DemoOfferId(BaseModel):
    offer_id: str = Field(min_length=32, max_length=32)


class DemoCommand(BaseModel):
    command: str = Field(min_length=8, max_length=250)
    confirmed: bool = False


def register_demo_routes(app: FastAPI, db_path: str | Path) -> None:
    store = DemoStore(db_path)

    def invoke(callback, *args, **kwargs):
        try:
            return callback(*args, **kwargs)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/demo", response_class=HTMLResponse)
    def demo_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "demo.html", {})

    @app.get("/api/demo/status")
    def status():
        return store.status()

    @app.get("/api/demo/config")
    def configuration():
        return {
            "mode": "DEMO_FIXTURE", "all_external_apis_disabled": True,
            "credentials_required": False, "network_requests": 0,
            "simulated_ai": "RULE_BASED_STAND_IN",
            "simulated_delivery": "LOCAL_SQLITE_RECEIPTS_ONLY",
            "notice": "Live SerpApi, Groq/OpenAI, email and Telegram are not contacted.",
        }

    @app.get("/api/demo/search")
    def search(q: str = Query(..., min_length=2, max_length=120),
               budget: str = Query("100000", max_length=30),
               limit: int = Query(30, ge=1, le=50)):
        return invoke(store.search, q, budget, limit=limit)

    @app.get("/api/demo/catalog")
    def catalog():
        return store.catalog()

    @app.get("/api/demo/history/{offer_id}")
    def history(offer_id: str):
        return invoke(store.history, offer_id)

    @app.get("/api/demo/analysis/{offer_id}")
    def analysis(offer_id: str, budget: str = Query(..., max_length=30)):
        return invoke(store.analyze, offer_id, budget)

    @app.get("/api/demo/explain/{offer_id}")
    def explain(offer_id: str, budget: str = Query(..., max_length=30)):
        return invoke(store.explain, offer_id, budget)

    @app.get("/api/demo/diagnostics")
    def diagnostics():
        return store.audit()

    @app.get("/api/demo/watches")
    def watches():
        return store.watches()

    @app.post("/api/demo/watch")
    def add_watch(body: DemoWatchRequest):
        return invoke(store.add_watch, body.query, body.budget,
                      body.channel, confirmed=body.confirmed)

    @app.post("/api/demo/watch/{watch_id}/disable")
    def disable_watch(watch_id: str):
        return store.disable_watch(watch_id)

    @app.post("/api/demo/poll")
    def poll(body: Confirmation):
        return invoke(store.poll_once, confirmed=body.confirmed)

    @app.get("/api/demo/alerts")
    def alerts():
        return store.alerts()

    @app.post("/api/demo/dispatch")
    def dispatch(body: Confirmation):
        return invoke(store.dispatch, confirmed=body.confirmed)

    @app.get("/api/demo/learning")
    def learning():
        return store.learning()

    @app.post("/api/demo/learning")
    def enable_learning(body: DemoLearningToggle):
        return invoke(store.learning_enable, body.enabled, confirmed=body.confirmed)

    @app.post("/api/demo/feedback")
    def feedback(body: DemoFeedback):
        return invoke(store.feedback, body.offer_id, body.preference)

    @app.post("/api/demo/forget")
    def forget(body: DemoOfferId):
        return store.forget(body.offer_id)

    @app.post("/api/demo/clear")
    def clear(body: Confirmation):
        return invoke(store.clear, confirmed=body.confirmed)

    @app.post("/api/demo/assistant")
    def assistant(body: DemoCommand):
        return invoke(store.assistant, body.command, confirmed=body.confirmed)
