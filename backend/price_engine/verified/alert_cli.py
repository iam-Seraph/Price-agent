"""Local operator CLI for opt-in email and Telegram alerts."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from .alert_store import AlertStore
from .delivery import deliver_due

ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Price Agent alert subscriptions and delivery")
    parser.add_argument("--db", default="tracker.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    enable = commands.add_parser("enable")
    enable.add_argument("watch_id")
    enable.add_argument("--channel", choices=["EMAIL", "TELEGRAM"], required=True)
    disable = commands.add_parser("disable")
    disable.add_argument("watch_id")
    disable.add_argument("--channel", choices=["EMAIL", "TELEGRAM"], required=True)
    commands.add_parser("list")
    commands.add_parser("outbox")
    send = commands.add_parser("dispatch")
    send.add_argument("--limit", type=int, default=5)
    send.add_argument("--continuous", action="store_true")
    send.add_argument("--sleep-seconds", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        store = AlertStore(args.db)
        if args.command in ("enable", "disable"):
            rule_id = store.set_channel(args.watch_id, args.channel,
                         enabled=args.command == "enable")
            result = {"rule_id": rule_id, "enabled": args.command == "enable"}
        elif args.command == "list":
            result = {"rules": store.list_rules()}
        elif args.command == "outbox":
            result = {"deliveries": store.list_deliveries()}
        else:
            if not 1 <= args.limit <= 10 or not 15 <= args.sleep_seconds <= 3600:
                parser.error("Delivery limit must be 1-10 and delay 15-3600 seconds")
            if not args.continuous:
                result = {"results": deliver_due(store, limit=args.limit)}
            else:
                print("Starting explicit delivery worker. Ctrl+C stops it.", flush=True)
                try:
                    while True:
                        result = {"results": deliver_due(store, limit=args.limit)}
                        print(json.dumps(result, ensure_ascii=False), flush=True)
                        time.sleep(args.sleep_seconds)
                except KeyboardInterrupt:
                    print(json.dumps({"stopped": True}))
                    return 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
