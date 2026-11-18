"""Deterministic, fail-closed deal decisions from stored provider observations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .money import format_minor, minor_units
from .store import VerifiedPriceStore


def _stamp(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Analysis clock must be timezone-aware")
    return moment.astimezone(timezone.utc).isoformat(
        timespec="microseconds").replace("+00:00", "Z")


def analyze_offer(store: VerifiedPriceStore, offer_id: str, budget: str | int | Decimal,
                  *, now: datetime | None = None, min_unique_days: int = 10) -> dict[str, Any]:
    """No model decision can promote unknown, old or sparse evidence to ALERT."""
    if not isinstance(offer_id, str) or len(offer_id) != 64:
        raise ValueError("Valid offer ID is required")
    if type(min_unique_days) is not int or not 1 <= min_unique_days <= 30:
        raise ValueError("Unique-day threshold must be 1-30")
    moment = now or datetime.now(timezone.utc)
    end = _stamp(moment)
    since = _stamp(moment - timedelta(days=30))
    offer = store.offer(offer_id)
    if offer is None:
        raise ValueError("Unknown offer; ingest a real provider result first")
    currency = str(offer["currency"])
    budget_minor = minor_units(budget, currency)
    with store.connect() as db:
        latest = db.execute("""
            SELECT observed_at,price_minor,stock,seller_rating,evidence_sha256,provenance
            FROM verified_offer_observations
            WHERE offer_id=? AND observed_at<=?
            ORDER BY observed_at DESC,event_id DESC LIMIT 1
        """, (offer_id,end)).fetchone()
        window = db.execute("""
            SELECT COUNT(*) AS samples, COUNT(DISTINCT substr(observed_at,1,10)) AS days,
                   COALESCE(SUM(price_minor),0) AS total_minor,
                   MIN(price_minor) AS low_minor
            FROM verified_offer_observations
            WHERE offer_id=? AND observed_at>=? AND observed_at<=?
        """, (offer_id,since,end)).fetchone()
        all_time_low = db.execute("""
            SELECT MIN(price_minor) FROM verified_offer_observations
            WHERE offer_id=? AND observed_at<=?
        """, (offer_id,end)).fetchone()[0]
    if latest is None:
        raise ValueError("No observed prices for offer")
    current = int(latest["price_minor"])
    samples = int(window["samples"])
    days = int(window["days"])
    total = int(window["total_minor"])
    low = int(window["low_minor"]) if window["low_minor"] is not None else None
    current_at = datetime.fromisoformat(str(latest["observed_at"]).replace("Z","+00:00"))
    stale = (moment.astimezone(timezone.utc) - current_at).total_seconds() > 24 * 3600
    rating = (Decimal(str(latest["seller_rating"]))
              if latest["seller_rating"] is not None else None)
    checks = {
        "under_budget": current <= budget_minor,
        "recent_evidence": not stale,
        "history_depth": days >= min_unique_days and samples >= min_unique_days,
        "below_30d_average": bool(samples and current * samples * 10 <= total * 9),
        "near_30d_low": bool(low is not None and current * 20 <= low * 21),
        "stock_confirmed": latest["stock"] == "IN_STOCK",
        "seller_evidence": bool(rating is not None and Decimal("4") <= rating <= Decimal("5")),
        "provider_provenance": latest["provenance"] == "PROVIDER_REPORTED",
    }
    decision = "ALERT" if all(checks.values()) else "NO_ALERT"
    return {
        "offer_id": offer_id, "name": offer["title"], "merchant": offer["merchant"],
        "url": offer["product_url"], "currency": currency,
        "price_minor": current, "price": format_minor(current, currency),
        "budget_minor": budget_minor, "budget": format_minor(budget_minor, currency),
        "last_observed_at": str(latest["observed_at"]),
        "evidence_sha256": str(latest["evidence_sha256"]),
        "source": str(offer["provider"]), "provenance": str(latest["provenance"]),
        "sample_count_30d": samples, "unique_days_30d": days,
        "average_30d_minor": (total // samples if samples else None),
        "low_30d_minor": low, "all_time_low_minor": all_time_low,
        "stock": str(latest["stock"]),
        "seller_rating": str(rating) if rating is not None else None,
        "checks": checks,
        "decision": decision,
        "failed_checks": [name for name, ok in checks.items() if not ok],
        "notice": "Provider-reported prices; no independent merchant validation or forecast.",
    }
