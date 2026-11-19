"""Interpret a small, explicit shopping-command grammar locally."""
from __future__ import annotations

import argparse
import json

from .assistant import execute_command, plan_command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or confirm a safe price research command")
    parser.add_argument("command", help="Quoted command, e.g. watch headphones below ₹3000")
    parser.add_argument("--db", default="tracker.sqlite3")
    parser.add_argument("--confirm", action="store_true",
                        help="Explicitly approve saving a watch; no worker starts")
    args = parser.parse_args(argv)
    try:
        result = (execute_command(args.db, args.command, confirmed=True)
                  if args.confirm else plan_command(args.command))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
