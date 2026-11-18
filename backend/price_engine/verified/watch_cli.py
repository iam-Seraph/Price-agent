"""Local-only command-line watch manager and bounded polling worker."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from .monitor import run_due_once
from .watch_store import WatchStore

ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Price Agent local watch manager")
    parser.add_argument("--db", default="tracker.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="Save a product query and price threshold")
    add.add_argument("query")
    add.add_argument("--budget", required=True)
    add.add_argument("--currency", choices=["INR", "USD"], default="INR")
    add.add_argument("--interval-minutes", type=int, default=60)
    commands.add_parser("list", help="List saved watch rules (no network access)")
    disable = commands.add_parser("disable", help="Stop monitoring one saved rule")
    disable.add_argument("watch_id")
    run = commands.add_parser("run", help="Poll due watches when explicitly started")
    run.add_argument("--batch-size", type=int, default=1)
    run.add_argument("--continuous", action="store_true")
    run.add_argument("--sleep-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        store = WatchStore(args.db)
        if args.command == "add":
            watch_id = store.add_watch(args.query, args.budget,
                args.currency, args.interval_minutes)
            result = {"watch_id": watch_id, "saved": True}
        elif args.command == "list":
            result = {"watches": store.list_watches()}
        elif args.command == "disable":
            result = {"disabled": store.disable_watch(args.watch_id)}
        else:
            if not 1 <= args.batch_size <= 5 or not 15 <= args.sleep_seconds <= 3600:
                parser.error("Batch size must be 1-5 and loop delay 15-3600 seconds")
            if not args.continuous:
                result = {"runs": run_due_once(store, limit=args.batch_size)}
            else:
                print("Starting opt-in price monitor. Ctrl+C stops it.", flush=True)
                try:
                    while True:
                        result = {"runs": run_due_once(store, limit=args.batch_size)}
                        print(json.dumps(result, ensure_ascii=False), flush=True)
                        time.sleep(args.sleep_seconds)
                except KeyboardInterrupt:
                    print(json.dumps({"stopped": True}))
                    return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
