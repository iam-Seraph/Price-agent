"""Check that local Markdown links resolve after documentation moves.

External URLs and section-only fragments are ignored. No third-party libraries needed.
Run from any working directory: python scripts/check_doc_links.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(?<!!)\[[^\]]+\]\((<[^>]+>|[^)\s]+)(?:\s+['\"][^)]*['\"])?\)")
SKIP = {".git", ".venv", ".pytest_cache", "node_modules", "__pycache__"}


def main() -> int:
    errors: list[str] = []
    count = 0
    for document in ROOT.rglob("*.md"):
        if any(part in SKIP for part in document.relative_to(ROOT).parts):
            continue
        for match in LINK.finditer(document.read_text(encoding="utf-8")):
            raw = match.group(1).strip("<>")
            if raw.startswith("#") or raw.startswith(("mailto:", "data:")):
                continue
            parsed = urlsplit(raw)
            if parsed.scheme or parsed.netloc:
                continue
            target = unquote(parsed.path)
            if not target:
                continue
            count += 1
            resolved = (document.parent / target).resolve()
            if not resolved.is_relative_to(ROOT):
                errors.append(f"{document.relative_to(ROOT)}: link escapes repository: {raw}")
            elif not resolved.exists():
                errors.append(f"{document.relative_to(ROOT)}: missing {raw}")
    for error in errors:
        print(f"ERROR {error}")
    print(f"Checked {count} local Markdown link(s) in repository.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
