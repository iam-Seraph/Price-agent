"""Explain the basis of price research without AI-generated prices."""
from __future__ import annotations

from typing import Any


def explain_candidates(research: dict[str, Any]) -> dict[str, Any]:
    offers = research.get("results")
    if not isinstance(offers, list):
        raise ValueError("Expected stored research results")
    summaries: list[dict[str, Any]] = []
    for offer in offers:
        if not isinstance(offer, dict):
            raise ValueError("Each offer must have grounded fields")
        checks: list[str] = []
        if offer["freshness"] != "FRESH":
            checks.append("stale_or_future_observation")
        if offer["stock"] != "IN_STOCK":
            checks.append("stock_not_confirmed")
        if not offer["under_budget"]:
            checks.append("over_budget")
        if offer["seller_rating"] is None:
            checks.append("seller_rating_unavailable")
        if offer["unique_days_30d"] < 10:
            checks.append("short_history")
        checks.extend("deal_" + str(x) for x in offer["unmet_deal_checks"])
        confidence = (
            "EVIDENCE_BACKED_DEAL" if offer["historical_deal"] == "ALERT"
            else "PRICE_ONLY_CANDIDATE" if offer["budget_candidate"]
            else "INSUFFICIENT_EVIDENCE"
        )
        summaries.append({
            "offer_id": offer["offer_id"],
            "title": offer["title"], "merchant": offer["merchant"],
            "price_display": offer["price_display"],
            "research_class": confidence,
            "cautions": sorted(set(checks)),
        })
    return {
        "query": research["query"], "results": summaries,
        "method": "Deterministic checks over provider-reported persisted prices only",
        "not_a_forecast": True,
    }
