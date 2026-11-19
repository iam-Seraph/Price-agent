"""Operator-controlled local preference memory (never runs background jobs)."""
from __future__ import annotations

import argparse
import json

from .learning import LearningStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage opt-in offer preferences")
    parser.add_argument("--db", default="tracker.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    for action in ("enable", "disable", "clear"):
        commands.add_parser(action).add_argument(
            "--confirm", action="store_true", help="Confirm intentional privacy change")
    for action in ("prefer", "avoid", "forget"):
        commands.add_parser(action).add_argument("offer_id")
    args = parser.parse_args(argv)
    try:
        store = LearningStore(args.db)
        if args.command == "status":
            result = store.status()
        elif args.command in ("enable", "disable"):
            result = store.set_enabled(args.command == "enable", confirmed=args.confirm)
        elif args.command == "clear":
            result = store.clear_all(confirmed=args.confirm)
        elif args.command == "forget":
            result = {"removed": store.forget_offer(args.offer_id)}
        else:
            result = store.give_feedback(args.offer_id, args.command.upper().replace("PREFER", "PREFER").replace("AVOID", "AVOID"))
        print(json.dumps(result, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
