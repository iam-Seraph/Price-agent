"""Deterministic comparisons of *distinct* source-attributed listings."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def comparison_table(research: dict[str, Any]) -> dict[str, Any]:
    """Rank comparable price *observations*, never claim identical product models."""
    products = research.get("results")
    if not isinstance(products, list):
        raise ValueError("Research records must be a list")
    rows = []
    by_merchant: dict[str, list[int]] = defaultdict(list)
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("price_minor"), int):
            raise ValueError("Invalid stored research data")
        row = {
            "offer_id": product["offer_id"],
            "merchant": product["merchant"],
            "title": product["title"],
            "currency": product["currency"],
            "price_minor": product["price_minor"],
            "price_display": product["price_display"],
            "stock": product["stock"],
            "freshness": product["freshness"],
            "budget_candidate": product["budget_candidate"],
            "source_url": product["source_url"],
        }
        rows.append(row)
        by_merchant[str(product["merchant"])].append(int(product["price_minor"]))
    rows.sort(key=lambda row: (
        not row["budget_candidate"], row["price_minor"], str(row["merchant"]).casefold(),
        str(row["offer_id"])
    ))
    return {
        "query": research["query"], "currency": research["currency"],
        "rows": rows, "merchant_count": len(by_merchant),
        "not_product_equivalence": True,
        "notice": "Prices are for independently identified retail listings, not guaranteed identical specifications, condition, warranty or variant.",
    }
