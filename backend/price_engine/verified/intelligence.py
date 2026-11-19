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


def detect_price_anomaly(store: VerifiedPriceStore, offer_id: str, *,
                         now: datetime | None = None) -> dict[str, Any]:
    """Report abrupt price changes against earlier observed daily medians."""
    history = daily_series(store, offer_id, days=90, now=now)
    daily = history["series"]
    observations = store.history(offer_id, days=90, limit=1000)
    clock = now or datetime.now(timezone.utc)
    eligible = [row for row in observations
                if datetime.fromisoformat(
                    str(row["observed_at"]).replace("Z","+00:00")) <= clock]
    if not eligible:
        raise ValueError("No recorded provider prices available")
    current = eligible[-1]
    current_minor = int(current["price_minor"])
    current_day = str(current["observed_at"])[:10]
    before = [int(row["daily_median_minor"]) for row in daily
              if str(row["date"]) < current_day][-30:]
    if len(before) < 9:
        return {
            "offer_id": offer_id, "status": "INSUFFICIENT_PRIOR_DAYS",
            "prior_days": len(before), "is_anomaly": False,
            "current_price_minor": current_minor,
            "baseline_minor": None, "source": "PROVIDER_REPORTED",
        }
    baseline = int(median_low(before))
    abrupt_drop = current_minor * 100 < baseline * 60
    abrupt_rise = current_minor * 100 > baseline * 160
    reason = ("SHARP_PRICE_DROP" if abrupt_drop else
              "SHARP_PRICE_INCREASE" if abrupt_rise else "NORMAL_RANGE")
    return {
        "offer_id": offer_id,
        "status": reason, "prior_days": len(before),
        "current_price_minor": current_minor,
        "baseline_minor": baseline,
        "is_anomaly": abrupt_drop or abrupt_rise,
        "source": "PROVIDER_REPORTED",
        "notice": "Anomaly thresholds flag suspicious changes; they do not prove price manipulation.",
    }
