"""Run the repository's complete *offline* regression checks from any cwd.

Use after installation:
  python -m pip install -r backend/requirements-workspace.txt -r backend/requirements-dev.txt
  python scripts/full_check.py

No API credentials, remote shopping queries, real email or payment are required.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def main() -> int:
    python = sys.executable
    checks = [
        ("Documentation links", [python, "scripts/check_doc_links.py"], ROOT),
        ("Backend pytest suite", [python, "-m", "pytest", "-q", "tests"], BACKEND),
        ("Backend unittest suite",
         [python, "-m", "unittest", "discover", "-s", "tests", "-v"], BACKEND),
        ("Python compilation",
         [python, "-m", "compileall", "-q",
          "price_agent.py", "real_price_agent.py", "live_price.py",
          "price_agent_workspace.py", "price_watch.py", "price_alert.py",
          "price_research.py", "price_assistant.py", "price_intelligence.py",
          "price_audit.py", "src", "backend/price_engine", "backend/tests", "scripts"],
         ROOT),
        ("Studio JS syntax", ["node", "--check",
                              "backend/price_engine/static/intelligence.js"], ROOT),
        ("Studio worker JS syntax", ["node", "--check",
                                     "backend/price_engine/static/intelligence.worker.js"], ROOT),
        ("Verified UI JS syntax", ["node", "--check",
                                    "backend/price_engine/static/verified.js"], ROOT),
        ("Static site JS syntax", ["node", "--check", "site/script.js"], ROOT),
        ("Studio Node worker tests",
         ["node", "--test", "backend/tests/test_intelligence_worker.cjs"], ROOT),
    ]
    failed: list[str] = []
    for title, argv, cwd in checks:
        print(f"\n=== {title} ===", flush=True)
        try:
            status = subprocess.run(argv, cwd=cwd, check=False).returncode
        except OSError as exc:
            print(f"Cannot start check: {type(exc).__name__}", flush=True)
            status = 1
        if status:
            failed.append(title)
        print(f"{title}: {'FAIL' if status else 'PASS'}", flush=True)

    print(f"\nOffline validation: {len(checks) - len(failed)}/{len(checks)} passed")
    if failed:
        print("Failed checks: " + ", ".join(failed))
    print("Scope: offline fixtures only; no live provider, Groq, SMTP or production load verification.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
