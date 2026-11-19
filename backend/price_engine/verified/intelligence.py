"""Bounded, read-only historical intelligence from actual provider observations.

No interpolation, speculative forecasts, or synthetic prices are used.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median_low
from typing import Any

from .store import VerifiedPriceStore

MAX_OBSERVATIONS = 1000


def _clock(now: datetime | None) -> datetime:
    clock = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Clock must be timezone-aware")
    return clock.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def _observations(store: VerifiedPriceStore, offer_id: str, *,
                  days: int = 90, now: datetime | None = None) -> list[dict[str, Any]]:
    """Select newest bounded rows in a caller-controlled UTC window, then sort ascending."""
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError("Lookback must be between 1 and 365 days")
    clock = _clock(now)
    if store.offer(offer_id) is None:
        raise ValueError("Offer must exist in the provider history database")
    with store.connect() as db:
        rows = db.execute("""
            SELECT * FROM (
                SELECT observed_at,price_minor,stock,provenance,seller_rating
                FROM verified_offer_observations
                WHERE offer_id=? AND observed_at>=? AND observed_at<=?
                ORDER BY observed_at DESC,event_id DESC LIMIT ?
            )
            ORDER BY observed_at ASC
        """, (offer_id, _stamp(clock - timedelta(days=days)),
              _stamp(clock), MAX_OBSERVATIONS)).fetchall()
    return [dict(row) for row in rows]


def daily_series(store: VerifiedPriceStore, offer_id: str, *, days: int = 90,
                 now: datetime | None = None) -> dict[str, Any]:
    """Group observed in-stock prices by UTC day, using daily lower medians."""
    rows = _observations(store, offer_id, days=days, now=now)
    offer = store.offer(offer_id)
    assert offer is not None
    grouped: dict[str, list[int]] = defaultdict(list)
    discarded = 0
    for row in rows:
        if row["stock"] != "IN_STOCK" or row["provenance"] != "PROVIDER_REPORTED":
            discarded += 1
            continue
        observed = datetime.fromisoformat(str(row["observed_at"]).replace("Z", "+00:00"))
        day = observed.astimezone(timezone.utc).date().isoformat()
        grouped[day].append(int(row["price_minor"]))
    series = [
        {"date": day, "daily_median_minor": int(median_low(prices)),
         "observations": len(prices), "source": "PROVIDER_REPORTED"}
        for day, prices in sorted(grouped.items())
    ]
    return {
        "offer_id": offer_id, "title": offer["title"],
        "merchant": offer["merchant"], "currency": offer["currency"],
        "days_considered": days, "observed_days": len(series),
        "records_examined": len(rows), "records_discarded": discarded,
        "truncated_to_latest_1000": len(rows) == MAX_OBSERVATIONS,
        "series": series, "provenance": "PROVIDER_REPORTED",
        "notice": "Only actual in-stock provider observations; no missing dates or prices are invented.",
    }


def detect_price_anomaly(store: VerifiedPriceStore, offer_id: str, *,
                         now: datetime | None = None) -> dict[str, Any]:
    """Flag unusual changes only when fresh current and prior-day evidence exists."""
    clock = _clock(now)
    rows = _observations(store, offer_id, days=90, now=clock)
    if not rows:
        return {"offer_id": offer_id, "status": "NO_OBSERVATIONS",
                "is_anomaly": False, "prior_days": 0, "source": "PROVIDER_REPORTED"}
    latest = rows[-1]
    stamp = datetime.fromisoformat(str(latest["observed_at"]).replace("Z", "+00:00"))
    current_good = (latest["stock"] == "IN_STOCK"
                    and latest["provenance"] == "PROVIDER_REPORTED")
    if not current_good:
        return {"offer_id": offer_id, "status": "UNVERIFIED_CURRENT_PRICE",
                "is_anomaly": False, "prior_days": 0,
                "current_price_minor": None, "source": "PROVIDER_REPORTED"}
    current_minor = int(latest["price_minor"])
    if (clock - stamp.astimezone(timezone.utc)).total_seconds() > 24 * 3600:
        return {"offer_id": offer_id, "status": "STALE_CURRENT_PRICE",
                "is_anomaly": False, "prior_days": 0,
                "current_price_minor": current_minor, "source": "PROVIDER_REPORTED"}
    history = daily_series(store, offer_id, days=90, now=clock)
    current_day = stamp.astimezone(timezone.utc).date().isoformat()
    before = [int(row["daily_median_minor"]) for row in history["series"]
              if str(row["date"]) < current_day][-30:]
    if len(before) < 10:
        return {"offer_id": offer_id, "status": "INSUFFICIENT_PRIOR_DAYS",
                "prior_days": len(before), "is_anomaly": False,
                "current_price_minor": current_minor,
                "baseline_minor": None, "source": "PROVIDER_REPORTED"}
    baseline = int(median_low(before))
    drop = current_minor * 100 < baseline * 60
    rise = current_minor * 100 > baseline * 160
    status = "SHARP_PRICE_DROP" if drop else (
        "SHARP_PRICE_INCREASE" if rise else "NORMAL_RANGE")
    return {
        "offer_id": offer_id, "status": status,
        "prior_days": len(before), "current_price_minor": current_minor,
        "baseline_minor": baseline, "is_anomaly": drop or rise,
        "source": "PROVIDER_REPORTED",
        "notice": "Heuristic anomaly flag, not proof of seller manipulation or a price forecast.",
    }


def price_trend(store: VerifiedPriceStore, offer_id: str, *,
                now: datetime | None = None) -> dict[str, Any]:
    """Compare observed medians in two consecutive 7-day periods, without prediction."""
    clock = _clock(now)
    rows = daily_series(store, offer_id, days=14, now=clock)
    midpoint = (clock - timedelta(days=7)).date().isoformat()
    old = [int(x["daily_median_minor"]) for x in rows["series"] if x["date"] < midpoint]
    recent = [int(x["daily_median_minor"]) for x in rows["series"] if x["date"] >= midpoint]
    if len(old) < 3 or len(recent) < 3:
        return {"offer_id": offer_id, "status": "INSUFFICIENT_HISTORY",
                "direction": "UNKNOWN", "older_days": len(old),
                "recent_days": len(recent), "source": "PROVIDER_REPORTED"}
    old_med, new_med = median_low(old), median_low(recent)
    direction = "LOWER" if new_med < old_med else ("HIGHER" if new_med > old_med else "UNCHANGED")
    return {
        "offer_id": offer_id, "status": "OBSERVED",
        "direction": direction, "older_median_minor": int(old_med),
        "recent_median_minor": int(new_med), "older_days": len(old),
        "recent_days": len(recent), "source": "PROVIDER_REPORTED",
        "notice": "Past observed trend only; no future price forecast.",
    }
