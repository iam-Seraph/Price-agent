"""Offline research over stored, source-attributed product offers."""
from __future__ import annotations

import argparse
import json

from .comparison import comparison_table
from .explanations import explain_candidates
from .research import research_offers
from .store import VerifiedPriceStore
from .learning import LearningStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research previously observed real offers")
    parser.add_argument("query", help="Product name keyword in stored offers")
    parser.add_argument("--db", default="tracker.sqlite3")
    parser.add_argument("--budget", required=True)
    parser.add_argument("--currency", choices=("INR", "USD"), default="INR")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args(argv)
    try:
        store = VerifiedPriceStore(args.db)
        records = research_offers(store, args.query, args.budget,
                                  currency=args.currency, limit=args.limit,
                                  learning=LearningStore(args.db))
        result = {
            "research": records,
            "comparison": comparison_table(records),
            "explanations": explain_candidates(records),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
