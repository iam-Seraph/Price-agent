"""Audit the local Price Agent SQLite database without contacting providers."""
from __future__ import annotations

import argparse
import json
import sqlite3

from .audit import audit_store
from .store import VerifiedPriceStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Price Agent release-readiness audit")
    parser.add_argument("--db", default="tracker.sqlite3")
    args = parser.parse_args(argv)
    try:
        store = VerifiedPriceStore(args.db, initialize=False)
        result = audit_store(store)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 2
    except (ValueError, sqlite3.DatabaseError, OSError) as exc:
        print(json.dumps({"status": "ERROR", "message": "Local database audit failed",
                          "type": type(exc).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
