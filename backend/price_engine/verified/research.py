"""Read-only shopping research over provider-attributed SQLite observations."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from .money import format_minor, minor_units, validate_currency
from .analysis import analyze_offer
from .store import VerifiedPriceStore


def research_offers(store: VerifiedPriceStore, query: str, budget: str | int | Decimal,
                    *, currency: str = "INR", limit: int = 30,
                    now: datetime | None = None) -> dict[str, Any]:
    """Find products; never merge different retailer SKUs into a single identity."""
    currency = validate_currency(currency)
    budget_minor = minor_units(budget, currency)
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Research timestamp must be timezone-aware")
    rows = store.find_offers(query, currency, limit=limit)
    output: list[dict[str, Any]] = []
    for row in rows:
        observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
        age = (clock.astimezone(timezone.utc) - observed).total_seconds()
        freshness = "FRESH" if 0 <= age <= 24*3600 else "STALE_OR_FUTURE"
        stock = str(row["stock"])
        candidate = bool(freshness == "FRESH" and stock == "IN_STOCK"
                         and int(row["price_minor"]) <= budget_minor
                         and row["provenance"] == "PROVIDER_REPORTED")
        verdict = analyze_offer(store, str(row["offer_id"]), budget, now=clock)
        output.append({
            "historical_deal": verdict["decision"],
            "sample_count_30d": verdict["sample_count_30d"],
            "unique_days_30d": verdict["unique_days_30d"],
            "unmet_deal_checks": verdict["failed_checks"],
            "offer_id": str(row["offer_id"]),
            "provider_product_id": str(row["provider_product_id"]),
            "title": str(row["title"]), "merchant": str(row["merchant"]),
            "source": str(row["provider"]),
            "source_url": str(row["product_url"]),
            "currency": currency,
            "price_minor": int(row["price_minor"]),
            "price_display": format_minor(int(row["price_minor"]), currency),
            "stock": stock, "seller_rating": row["seller_rating"],
            "observed_at": str(row["observed_at"]),
            "freshness": freshness,
            "under_budget": int(row["price_minor"]) <= budget_minor,
            "budget_candidate": candidate,
            "evidence_sha256": str(row["evidence_sha256"]),
            "provenance": str(row["provenance"]),
        })
    return {
        "query": query.strip(), "currency": currency,
        "budget_minor": budget_minor, "budget_display": format_minor(budget_minor,currency),
        "results": output, "matching_offers": len(output),
        "budget_candidates": sum(1 for row in output if row["budget_candidate"]),
        "notice": "Candidates are provider-reported individual offers. Distinct SKUs, sellers and variants are NOT confirmed equivalent. Stock, prices and seller facts require manual verification before purchase.",
        "generated_at": clock.astimezone(timezone.utc).isoformat(),
    }
