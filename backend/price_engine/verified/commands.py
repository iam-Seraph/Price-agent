"""Deterministic natural-language shopping intents; no implicit agent actions."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .money import format_minor, minor_units

_AMOUNT = r"(?P<unit>₹|INR|\$|USD)\s*(?P<amount>\d[\d,]*(?:\.\d{1,2})?)"
_PATTERNS = (
    ("CREATE_WATCH", re.compile(
        r"notify\s+me\s+when\s+(?P<query>.+?)\s+drops\s+below\s+" + _AMOUNT + r"\s*[.!]?\Z",
        flags=re.IGNORECASE)),
    ("CREATE_WATCH", re.compile(
        r"watch\s+(?P<query>.+?)\s+below\s+" + _AMOUNT + r"\s*[.!]?\Z",
        flags=re.IGNORECASE)),
    ("COMPARE_STORED", re.compile(
        r"compare\s+(?P<query>.+?)\s+under\s+" + _AMOUNT + r"\s*[.!]?\Z",
        flags=re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class ShoppingIntent:
    action: str
    query: str
    currency: str
    budget_minor: int
    budget_display: str
    requires_confirmation: bool

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_shopping_intent(text: str) -> ShoppingIntent:
    """Parse explicitly supported requests; reject unknown or ambiguous commands."""
    if not isinstance(text, str) or not 8 <= len(text.strip()) <= 250:
        raise ValueError("Command must be 8–250 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError("Control characters are not permitted")
    for action, pattern in _PATTERNS:
        match = pattern.fullmatch(text.strip())
        if match is None:
            continue
        query = match.group("query").strip()
        if not 2 <= len(query) <= 120:
            raise ValueError("Product query must be 2–120 characters")
        if query.startswith(("'", '"')) or query.endswith(("'", '"')):
            query = query.strip("\"'")
        if not 2 <= len(query) <= 120:
            raise ValueError("Invalid product name")
        currency = "INR" if match.group("unit").upper() in {"₹", "INR"} else "USD"
        minor = minor_units(match.group("amount"), currency)
        return ShoppingIntent(action, query, currency, minor,
                              format_minor(minor, currency),
                              action == "CREATE_WATCH")
    raise ValueError("Supported commands: watch X below ₹N; notify me when X drops below ₹N; compare X under ₹N")
