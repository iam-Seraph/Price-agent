"""Opt-in one-shot monitor; never contacts stores directly or starts on app import."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .provider import ProviderUnavailable, search_serpapi
from .types import ProviderOffer
from .watch_store import WatchStore, watch_time


def run_due_once(store: WatchStore, *, now: datetime | None = None,
                 limit: int = 1,
                 search: Callable[..., list[ProviderOffer]] = search_serpapi
                 ) -> list[dict[str, Any]]:
    """Process short leased batches and retain only real, source-backed offers."""
    claimed = store.claim_due(now=now, limit=limit)
    results = []
    for watch in claimed:
        watch["started_at"] = watch_time(now or datetime.now(timezone.utc))
        inspected = inserted = 0
        status = "ERROR"
        message = ""
        try:
            offers = search(str(watch["query_text"]), limit=5)
            if not isinstance(offers, list) or any(not isinstance(x, ProviderOffer) for x in offers):
                raise ValueError("Provider returned invalid offer objects")
            inspected = len(offers)
            matching = 0
            for offer in offers:
                if offer.currency != watch["currency"]:
                    continue
                matching += 1
                inserted += int(store.prices.persist(offer))
            status = "OK" if matching else "NO_MATCHES"
        except ProviderUnavailable:
            status = "PROVIDER_UNAVAILABLE"
            message = "Provider unavailable or access denied; no fake prices stored"
        except (ValueError, TypeError):
            status = "ERROR"
            message = "Provider data failed validation"
        finally:
            store.complete_claim(
                watch, status=status, offers_inspected=inspected,
                inserted_observations=inserted, message=message, now=now)
        results.append({
            "watch_id": str(watch["watch_id"]), "status": status,
            "offers_inspected": inspected, "inserted_observations": inserted,
            "provenance": "PROVIDER_REPORTED",
        })
    return results
