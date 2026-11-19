"""Conservative, on-demand integrity audit for one local provider-history database.

This is NOT an authentication, multi-tenant, or live-price verification service.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .store import VerifiedPriceStore


def audit_store(store: VerifiedPriceStore, *, now: datetime | None = None) -> dict[str, Any]:
    """Run bounded, local checks without requesting prices or altering stored rows."""
    clock = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(clock, datetime) or clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("Audit timestamp must be timezone-aware")
    future_limit = (clock.astimezone(timezone.utc) + timedelta(minutes=5)).isoformat(
        timespec="microseconds").replace("+00:00", "Z")
    with store.connect() as db:
        integrity = str(db.execute("PRAGMA quick_check(1)").fetchone()[0])
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchmany(10)
        counts = db.execute("""
            SELECT COUNT(*) AS observations,
                   COALESCE(SUM(CASE WHEN price_minor<=0 THEN 1 ELSE 0 END),0) AS invalid_prices,
                   COALESCE(SUM(CASE WHEN provenance!='PROVIDER_REPORTED' THEN 1 ELSE 0 END),0) AS invalid_provenance,
                   COALESCE(SUM(CASE WHEN observed_at>? THEN 1 ELSE 0 END),0) AS impossible_future
            FROM verified_offer_observations
        """, (future_limit,)).fetchone()
        offers = int(db.execute("SELECT COUNT(*) FROM verified_offers").fetchone()[0])
    checks = {
        "sqlite_quick_check": integrity == "ok",
        "no_foreign_key_violation": len(foreign_keys) == 0,
        "positive_observed_prices": int(counts["invalid_prices"]) == 0,
        "source_provenance": int(counts["invalid_provenance"]) == 0,
        "no_impossible_future_observations": int(counts["impossible_future"]) == 0,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "offers": offers,
        "observations": int(counts["observations"]),
        "invalid_prices": int(counts["invalid_prices"]),
        "invalid_provenance": int(counts["invalid_provenance"]),
        "impossible_future_observations": int(counts["impossible_future"]),
        "foreign_key_errors_at_least": len(foreign_keys),
        "database_scope": "SINGLE_OPERATOR",
        "multi_user_authorization_enabled": False,
        "provider_network_requests": 0,
        "note": "Local data integrity only. No live retail quote or merchant trust is verified.",
    }
