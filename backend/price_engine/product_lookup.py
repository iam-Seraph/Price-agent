"""Read-only agent product lookup: SerpApi -> DummyJSON -> bundled offline demo.

Only fixed API hosts are contacted; user-supplied URLs are never fetched.
Live shopping offers are not written into verified price history.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

_PACKAGE = Path(__file__).resolve().parent
load_dotenv(_PACKAGE.parents[1] / ".env", override=False)


def _float(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = float(str(value).replace(",", ""))
        return number if 0 <= number < 1e9 and number == number else None
    except (ValueError, TypeError, OverflowError):
        return None


def _rating(value: Any) -> float | None:
    number = _float(value)
    return number if number is not None and number <= 5 else None


def _int(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        number = int(str(value).replace(",", ""))
        return number if 0 <= number <= 10_000_000 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _serpapi(query: str) -> list[dict[str, Any]]:
    response = httpx.get("https://serpapi.com/search.json", params={
        "engine": "google_shopping", "q": query, "gl": "in", "hl": "en",
        "google_domain": "google.co.in", "api_key": os.environ["SERPAPI_KEY"]
    }, timeout=10.0, follow_redirects=False, trust_env=False)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("Shopping provider returned an error")
    offers = []
    for item in data.get("shopping_results", [])[:5]:
        if not isinstance(item, dict):
            continue
        price_text = str(item.get("price") or "")
        currency = "INR" if ("₹" in price_text or "INR" in price_text.upper()) else "UNKNOWN"
        stock = item.get("in_stock")
        offers.append({
            "name": str(item.get("title") or "Unnamed product")[:180],
            "price": _float(item.get("extracted_price")),
            "price_text": price_text[:80] or None,
            "currency": currency,
            "retailer": str(item.get("source") or "Unspecified seller")[:100],
            "availability": "IN_STOCK" if stock is True else "OUT_OF_STOCK" if stock is False else "UNKNOWN",
            "rating": _rating(item.get("rating")),
            "review_count": _int(item.get("reviews")),
            "review_highlights": [],
            "specs": {"highlights": str(item.get("extensions"))[:250]}
                     if item.get("extensions") else {},
            "url": item.get("link") if str(item.get("link") or "").startswith("https://") else None,
        })
    return offers


def _dummyjson(query: str) -> list[dict[str, Any]]:
    response = httpx.get("https://dummyjson.com/products/search", params={
        "q": query, "limit": 5
    }, timeout=8.0, follow_redirects=False, trust_env=False)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("products"), list):
        raise ValueError("Sample API returned invalid data")
    offers = []
    for item in data["products"][:5]:
        if not isinstance(item, dict):
            continue
        specs = {key: str(item[key])[:200] for key in (
            "description", "brand", "warrantyInformation", "shippingInformation"
        ) if item.get(key)}
        stock = _int(item.get("stock"))
        offers.append({
            "name": str(item.get("title") or "Unnamed product")[:180],
            "price": _float(item.get("price")), "price_text": None,
            "currency": "USD", "retailer": "DummyJSON sample catalog",
            "availability": "IN_STOCK" if stock and stock > 0 else "OUT_OF_STOCK" if stock == 0 else "UNKNOWN",
            "rating": _rating(item.get("rating")),
            "review_count": len(item["reviews"]) if isinstance(item.get("reviews"), list) else None,
            "review_highlights": [str(review.get("comment"))[:160] for review in item.get("reviews", [])[:2]
                                  if isinstance(review, dict) and review.get("comment")]
                                 if isinstance(item.get("reviews"), list) else [],
            "specs": specs, "url": None,
        })
    return offers


def _offline(query: str) -> list[dict[str, Any]]:
    rows = json.loads((_PACKAGE / "data" / "demo_products.json").read_text(encoding="utf-8"))
    matches = [r for r in rows if query.casefold() in r["name"].casefold()][:5]
    return [{"name": r["name"], "price": r["price"], "price_text": None,
             "currency": "INR", "retailer": r["retailer"],
             "availability": r["availability"], "rating": r.get("rating"),
             "review_count": r.get("review_count"), "review_highlights": [],
             "specs": r.get("specs", {}), "url": None} for r in matches]


def lookup_product(query: str) -> dict[str, Any]:
    """Tool entry point for the web UI or an LLM function-call dispatcher.

    This is research data only. Never treat it as certified deal history.
    """
    query = query.strip()
    if not 2 <= len(query) <= 120:
        raise ValueError("Search query must be 2–120 characters")
    warnings: list[str] = []
    checked = datetime.now(timezone.utc).isoformat()
    if os.getenv("SERPAPI_KEY", "").strip():
        try:
            return {"provider": "SERPAPI_GOOGLE_SHOPPING", "live_retailer_data": True,
                    "retrieved_at_utc": checked, "offers": _serpapi(query),
                    "warnings": warnings,
                    "notice": "Provider results may be delayed. Verify stock and price with the seller."}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            warnings.append("SerpApi unavailable; switched to sample-data fallback")
    try:
        offers = _dummyjson(query)
        if offers:
            return {"provider": "DUMMYJSON_SAMPLE_API", "live_retailer_data": False,
                    "retrieved_at_utc": checked, "offers": offers,
                    "warnings": warnings,
                    "notice": "DummyJSON provides sample products, not live retailer offers."}
        warnings.append("No sample API matches; checking bundled offline demo")
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        warnings.append("Sample API unavailable; using bundled offline demo")
    return {"provider": "OFFLINE_DEMO", "live_retailer_data": False,
            "retrieved_at_utc": checked, "offers": _offline(query),
            "warnings": warnings,
            "notice": "All offline prices, reviews and stock statuses are synthetic."}
