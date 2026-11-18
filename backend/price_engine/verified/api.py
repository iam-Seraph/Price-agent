"""Read-only real-provider offer routes for the existing local workspace."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .analysis import analyze_offer
from .store import VerifiedPriceStore

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates"))


def register_verified_routes(app: FastAPI, db_path: str | Path) -> None:
    """Install read-only endpoints; no retailer fetch is triggered by a GET."""
    store = VerifiedPriceStore(db_path)

    @app.get("/verified", response_class=HTMLResponse)
    def verified_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "verified.html", {})

    @app.get("/api/verified/status")
    def verified_status():
        return store.stats()

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
