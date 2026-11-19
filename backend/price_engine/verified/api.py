"""Explicit local write actions plus source-grounded read APIs."""
from __future__ import annotations

from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .money import minor_units
from .provider import ProviderUnavailable, search_serpapi

from .analysis import analyze_offer
from .alert_store import AlertStore
from .store import VerifiedPriceStore
from .watch_store import WatchStore

class VerifiedSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    budget: str = Field(min_length=1, max_length=30)
    currency: Literal["INR", "USD"] = "INR"
    limit: int = Field(default=5, ge=1, le=5)


class WatchCreateRequest(BaseModel):
    query: str = Field(min_length=2, max_length=120)
    budget: str = Field(min_length=1, max_length=30)
    currency: Literal["INR", "USD"] = "INR"
    interval_minutes: int = Field(default=60, ge=15, le=1440)


class AlertChannelRequest(BaseModel):
    watch_id: str = Field(min_length=32, max_length=32)
    channel: Literal["EMAIL", "TELEGRAM"]
    enabled: bool
    confirmed: bool


TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates"))


def register_verified_routes(app: FastAPI, db_path: str | Path) -> None:
    """Install local opt-in endpoints; GET requests never fetch retailer prices."""
    store = VerifiedPriceStore(db_path)
    search_lock = Lock()
    last_search = [0.0]
    watches = WatchStore(db_path)
    alerts = AlertStore(db_path)

    @app.get("/verified", response_class=HTMLResponse)
    def verified_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "verified.html", {})

    @app.post("/api/verified/search")
    def verified_search(body: VerifiedSearchRequest):
        """Explicitly initiated real-provider search; no synthetic fallback."""
        try:
            minor_units(body.budget, body.currency)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        with search_lock:
            now = monotonic()
            if last_search[0] and now - last_search[0] < 15:
                raise HTTPException(status_code=429, detail="Wait before the next provider search")
            last_search[0] = now
        try:
            offers = search_serpapi(body.query, limit=body.limit)
        except ProviderUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        analyses = []
        inserted = 0
        for offer in offers:
            if offer.currency != body.currency:
                continue
            inserted += int(store.persist(offer))
            analyses.append(analyze_offer(store, offer.offer_id, body.budget))
        return {"provider": "SERPAPI_GOOGLE_SHOPPING",
                "provenance": "PROVIDER_REPORTED", "inserted": inserted,
                "analyses": analyses}

    @app.get("/api/verified/status")
    def verified_status():
        return store.stats()

    @app.post("/api/verified/watches", status_code=201)
    def create_verified_watch(body: WatchCreateRequest):
        try:
            if watches.active_watch_count() >= 100:
                raise HTTPException(status_code=429, detail="Local watchlist capacity reached")
            watch_id = watches.add_watch(body.query, body.budget,
                                        body.currency, body.interval_minutes)
            return {"watch_id": watch_id, "saved": True, "polling_started": False}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/verified/watches/{watch_id}/disable")
    def disable_verified_watch(watch_id: str):
        try:
            changed = watches.disable_watch(watch_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not changed:
            raise HTTPException(status_code=404, detail="Enabled watch not found")
        return {"disabled": True}

    @app.get("/api/verified/watches")
    def list_verified_watches(limit: int = Query(100, ge=1, le=200)):
        return {"watches": watches.list_watches(limit)}

    @app.post("/api/verified/alerts/channel")
    def configure_verified_alert_channel(body: AlertChannelRequest):
        if not body.confirmed:
            raise HTTPException(status_code=422, detail="Explicit confirmation required")
        try:
            rule_id = alerts.set_channel(body.watch_id, body.channel,
                                         enabled=body.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"rule_id": rule_id, "enabled": body.enabled,
                "delivery_started": False}

    @app.get("/api/verified/alerts")
    def list_verified_alerts(limit: int = Query(50, ge=1, le=100)):
        """Read source-qualified queue state without exposing contact destinations."""
        return {"rules": alerts.list_rules(limit=limit),
                "deliveries": alerts.list_deliveries(limit=limit),
                "contacts_stored_in_database": False}

    @app.get("/api/verified/watch-runs")
    def verified_watch_audit(limit: int = Query(30, ge=1, le=100)):
        return {"runs": watches.recent_runs(limit=limit)}

    @app.get("/api/verified/offers")
    def list_verified_offers(limit: int = Query(20, ge=1, le=100)):
        return {"offers": store.list_offers(limit), "provenance": "PROVIDER_REPORTED"}

    @app.get("/api/verified/offers/{offer_id}/history")
    def verified_offer_history(offer_id: str,
                               days: int = Query(30, ge=1, le=365),
                               limit: int = Query(300, ge=1, le=1000)):
        if store.offer(offer_id) is None:
            raise HTTPException(status_code=404, detail="Stored offer not found")
        return {"offer_id": offer_id, "currency": store.offer(offer_id)["currency"],
                "observations": store.history(offer_id, days=days, limit=limit),
                "provenance": "PROVIDER_REPORTED"}

    @app.get("/api/verified/offers/{offer_id}/analysis")
    def verified_offer_analysis(offer_id: str, budget: str = Query(..., min_length=1, max_length=30),
                                currency: Literal["INR", "USD"] = "INR"):
        offer = store.offer(offer_id)
        if offer is None:
            raise HTTPException(status_code=404, detail="Stored offer not found")
        if offer["currency"] != currency:
            raise HTTPException(status_code=422, detail="Budget currency differs from offer currency")
        try:
            return analyze_offer(store, offer_id, budget)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
