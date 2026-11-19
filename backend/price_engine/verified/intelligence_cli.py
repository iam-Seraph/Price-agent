"""Read-only historical intelligence CLI; only stored provider observations."""
from __future__ import annotations

import argparse
import json

from .intelligence import daily_series, detect_price_anomaly, price_trend
from .quality import evidence_quality
from .store import VerifiedPriceStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect real stored price history")
    parser.add_argument("offer_id", help="64-character persisted provider offer ID")
    parser.add_argument("--db", default="tracker.sqlite3")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args(argv)
    try:
        store = VerifiedPriceStore(args.db)
        report = {
            "daily": daily_series(store, args.offer_id, days=args.days),
            "anomaly": detect_price_anomaly(store, args.offer_id),
            "trend": price_trend(store, args.offer_id),
            "evidence": evidence_quality(store, args.offer_id),
            "network_requests": 0,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
