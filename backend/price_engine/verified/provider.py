"""Network-isolated SerpApi shopping adapter, with no synthetic fallback.

A provider-reported shopping result is not independently verified stock,
seller reputation, or an approved historical deal.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

import httpx

from .money import provider_price
from .types import ProviderOffer, new_event_id, safe_evidence_url

ENDPOINT = "https://serpapi.com/search.json"


class ProviderUnavailable(RuntimeError):
    """Explicit absence or failure of live provider data."""


def parse_shopping_results(payload: dict[str, Any], observed_at: datetime,
                           limit: int = 5) -> list[ProviderOffer]:
    if not isinstance(payload, dict) or payload.get("error"):
        raise ProviderUnavailable("Shopping provider returned an invalid response")
    results = payload.get("shopping_results", [])
    if not isinstance(results, list):
        raise ProviderUnavailable("Shopping results must be an array")
    accepted: list[ProviderOffer] = []
    seen_offer_ids: set[str] = set()
    for item in results[: min(20, max(limit * 4, limit))]:
        if not isinstance(item, dict):
            continue
        try:
            merchant = item["source"]
            title = item["title"]
            if (not isinstance(merchant, str) or not merchant.strip()
                    or not isinstance(title, str) or not title.strip()):
                continue
            link = item.get("link") or item.get("product_link")
            if not isinstance(link, str):
                continue
            safe_evidence_url(link)
            minor, currency = provider_price(item["price"], item.get("extracted_price"))
            source_id = item.get("product_id")
            if isinstance(source_id, bool) or not isinstance(source_id, (str, int)) or not str(source_id).strip():
                # URL-backed identity avoids assigning a fabricated product ID.
                source_id = "url-" + sha256(link.encode("utf-8")).hexdigest()
            source_id = str(source_id).strip()
            if not re.fullmatch(r"[A-Za-z0-9._:/+-]{1,200}", source_id):
                continue
            raw_rating = item.get("seller_rating")
            seller_rating = None
            if raw_rating is not None and isinstance(raw_rating, (int, str, float)):
                try:
                    seller_rating = Decimal(str(raw_rating))
                except InvalidOperation:
                    continue
            # A product star rating is NOT a seller rating.
            stock = ("IN_STOCK" if item.get("in_stock") is True else
                     "OUT_OF_STOCK" if item.get("in_stock") is False else "UNKNOWN")
            checksum = sha256(json.dumps(item, sort_keys=True, ensure_ascii=False,
                                         default=str).encode("utf-8")).hexdigest()
            quote = ProviderOffer(
                provider="SERPAPI_GOOGLE_SHOPPING", source_product_id=source_id,
                merchant=merchant.strip(), title=title.strip(),
                product_url=link, currency=currency, price_minor=minor, stock=stock,
                seller_rating=seller_rating, observed_at=observed_at,
                evidence_sha256=checksum, event_id=new_event_id(),
            )
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if quote.offer_id in seen_offer_ids:
            continue
        seen_offer_ids.add(quote.offer_id)
        accepted.append(quote)
        if len(accepted) >= limit:
            break
    return accepted


def search_serpapi(query: str, *, api_key: str | None = None,
                   transport: httpx.BaseTransport | None = None,
                   limit: int = 5, retries: int = 2,
                   sleeper: Callable[[float], None] = time.sleep) -> list[ProviderOffer]:
    """Use one fixed API origin, with bounded retries only for transient failures."""
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120:
        raise ValueError("Search query must be 2-120 characters")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("Search limit must be between 1 and 10")
    if type(retries) is not int or not 0 <= retries <= 3:
        raise ValueError("Retries must be between 0 and 3")
    key = api_key or os.getenv("SERPAPI_KEY")
    if not key:
        raise ProviderUnavailable("SERPAPI_KEY is not configured; no live data available")
    with httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False,
                      transport=transport) as client:
        for attempt in range(retries + 1):
            try:
                response = client.get(ENDPOINT, params={
                    "engine": "google_shopping", "q": query.strip(), "gl": "in",
                    "hl": "en", "api_key": key,
                })
            except httpx.TransportError:
                if attempt < retries:
                    sleeper(0.25 * 2**attempt)
                    continue
                raise ProviderUnavailable("SerpApi network failure; no data accepted") from None
            if response.status_code in (401, 403, 429):
                raise ProviderUnavailable("SerpApi denied or throttled the request; no retry attempted")
            if 500 <= response.status_code < 600:
                if attempt < retries:
                    sleeper(0.25 * 2**attempt)
                    continue
                raise ProviderUnavailable("SerpApi service unavailable after bounded retries")
            try:
                response.raise_for_status()
                if len(response.content) > 2 * 1024 * 1024:
                    raise ProviderUnavailable("Provider response exceeds the parsing limit")
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                raise ProviderUnavailable("SerpApi response failed validation") from None
            return parse_shopping_results(payload, datetime.now(timezone.utc), limit=limit)
    raise ProviderUnavailable("No provider response available")
