"""Evidence completeness, never seller reputation or merchant safety."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .intelligence import _clock, _observations, daily_series
from .store import VerifiedPriceStore


def evidence_quality(store: VerifiedPriceStore, offer_id: str,
                     *, now: datetime | None = None) -> dict[str, Any]:
    clock = _clock(now)
    history = _observations(store, offer_id, days=90, now=clock)
    if not history:
        raise ValueError("No stored offer observations within the 90-day window")
    last = history[-1]
    seen = datetime.fromisoformat(str(last["observed_at"]).replace("Z", "+00:00"))
    fresh = 0 <= (clock - seen.astimezone(timezone.utc)).total_seconds() <= 24*3600
    series = daily_series(store, offer_id, days=90, now=clock)
    checks = {
        "source_provenance": last["provenance"] == "PROVIDER_REPORTED",
        "price_recorded": type(last["price_minor"]) is int and int(last["price_minor"]) > 0,
        "known_stock": last["stock"] in ("IN_STOCK", "OUT_OF_STOCK"),
        "seller_rating_reported": last["seller_rating"] is not None,
        "recent_observation": fresh,
        "history_depth": series["observed_days"] >= 10,
    }
    weights = {
        "source_provenance": 20, "price_recorded": 20,
        "known_stock": 15, "seller_rating_reported": 10,
        "recent_observation": 20, "history_depth": 15,
    }
    return {
        "offer_id": offer_id,
        "evidence_completeness_score": sum(weights[k] for k, ok in checks.items() if ok),
        "maximum_score": 100, "checks": checks,
        "merchant_reliability_score": None,
        "source": "PROVIDER_REPORTED",
        "notice": "Completeness of stored evidence only; no seller trust, product authenticity or safety rating.",
    }
