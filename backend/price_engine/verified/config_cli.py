"""Display local API configuration readiness without making network requests."""
from __future__ import annotations

import json

from dotenv import load_dotenv

from .configuration import ROOT, configuration_status


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Local API credential presence (never exposes keys)")
    parser.parse_args(argv)
    load_dotenv(ROOT / ".env", override=False)
    print(json.dumps(configuration_status(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
