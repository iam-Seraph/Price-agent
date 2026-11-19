"""Daily source-reported price series, without fictional historical samples."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import median_low
from typing import Any

from .store import VerifiedPriceStore


def daily_series(store: VerifiedPriceStore, offer_id: str, *, days: int = 90,
                 now: datetime | None = None) -> dict[str, Any]:
    """Aggregate observed in-stock prices into source-attributed daily medians."""
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError("Lookback must be between 1 and 365 days")
    offer = store.offer(offer_id)
    if offer is None:
        raise ValueError("Offer must exist in the real-provider history database")
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Clock must be timezone-aware")
    grouped: dict[str, list[int]] = defaultdict(list)
    discarded = 0
    for row in store.history(offer_id, days=days, limit=1000):
        observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
        if (observed > clock or row["stock"] != "IN_STOCK"
                or row["provenance"] != "PROVIDER_REPORTED"):
            discarded += 1
            continue
        grouped[observed.date().isoformat()].append(int(row["price_minor"]))
    series = [{
        "date": day,
        "daily_median_minor": int(median_low(prices)),
        "observations": len(prices),
        "source": "PROVIDER_REPORTED",
    } for day, prices in sorted(grouped.items())]
    return {
        "offer_id": offer_id,
        "title": offer["title"], "merchant": offer["merchant"],
        "currency": offer["currency"],
        "days_considered": days,
        "observed_days": len(series),
        "discarded_non_stock_or_future": discarded,
        "series": series,
        "provenance": "PROVIDER_REPORTED",
        "notice": "Daily medians use at most 1000 recent provider observations; no unobserved days are interpolated.",
    }
