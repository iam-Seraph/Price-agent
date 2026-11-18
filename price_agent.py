"""Backwards-compatible CLI entry point; implementation lives in src/price_agent.py."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parent / "src" / "price_agent.py"), run_name="__main__")
