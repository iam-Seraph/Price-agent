"""Real provider ingestion and SQLite-backed analysis CLI (no mock fallback)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .analysis import analyze_offer
from .money import validate_currency
from .provider import ProviderUnavailable, search_serpapi
from .store import VerifiedPriceStore
from .tool_agent import run_groq_react

ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Provider-reported price ingestion and historical analysis")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--query", help="Search Google Shopping through SerpApi")
    selector.add_argument("--offer-id", help="Analyze an already persisted offer")
    selector.add_argument("--list", action="store_true", help="List offers already stored")
    parser.add_argument("--db", default="tracker.sqlite3")
    parser.add_argument("--budget", help="Budget in the explicitly selected currency")
    parser.add_argument("--currency", choices=("INR", "USD"), default="INR")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--explain", action="store_true", help="Optional read-only Groq explanation")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.limit > 10:
        parser.error("--limit must be between 1 and 10")
    if not args.list and args.budget is None:
        parser.error("--budget is required for search and analysis")
    store = VerifiedPriceStore(args.db)
    if args.list:
        print(json.dumps({"offers": store.list_offers()}, indent=2))
        return 0
    try:
        if args.query is not None:
            quotes = search_serpapi(args.query, limit=args.limit)
            if not quotes:
                print(json.dumps({"status": "NO_PROVIDER_OFFERS", "stored": 0}))
                return 3
            ids = []
            stored = 0
            for quote in quotes:
                if quote.currency != validate_currency(args.currency):
                    continue
                stored += int(store.persist(quote))
                ids.append(quote.offer_id)
            if not ids:
                print(json.dumps({"status": "NO_MATCHING_CURRENCY", "stored": 0}))
                return 3
        else:
            selected = store.offer(args.offer_id)
            if selected is None:
                raise ValueError("Offer not found in local price history")
            if selected["currency"] != validate_currency(args.currency):
                raise ValueError("Budget currency does not match stored offer currency")
            ids = [args.offer_id]
            stored = 0
        reports = [analyze_offer(store, offer_id, args.budget) for offer_id in dict.fromkeys(ids)]
        output: dict[str, object] = {
            "status": "OK", "stored_new_events": stored, "currency": args.currency,
            "analyses": reports, "live_provider_called": args.query is not None,
        }
        if args.explain:
            key = os.environ.get("GROQ_API_KEY")
            if not key:
                raise ValueError("GROQ_API_KEY is required for optional AI explanation")
            from openai import OpenAI
            client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1",
                            timeout=20.0, max_retries=1)
            output["ai"] = run_groq_react(store, ids[0], args.budget, client,
                       model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except (ProviderUnavailable, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
