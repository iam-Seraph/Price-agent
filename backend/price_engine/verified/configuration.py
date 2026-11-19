"""Secret-safe configuration checks. Never network-test or echo API tokens."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[3]


def _configured(env: Mapping[str, str], name: str) -> bool:
    value = env.get(name, "").strip()
    if not value or len(value) > 8192:
        return False
    lowered = value.casefold()
    return not lowered.startswith((
        "replace_with", "your_", "paste_", "example_", "change_me", "placeholder"
    ))


def _status(env: Mapping[str, str], *names: str) -> str:
    return ("CONFIGURED_UNVERIFIED" if all(_configured(env, name) for name in names)
            else "NOT_CONFIGURED")


def configuration_status(env: Mapping[str, str] | None = None) -> dict[str, object]:
    """Check presence only; a configured token may still be invalid or rate-limited."""
    selected = os.environ if env is None else env
    return {
        "providers": {
            "google_shopping_serpapi": _status(selected, "SERPAPI_KEY"),
            "groq_explanations": _status(selected, "GROQ_API_KEY"),
            "legacy_openai_optional": _status(selected, "OPENAI_API_KEY"),
        },
        "notifications": {
            "telegram": _status(
                selected, "PRICE_AGENT_TELEGRAM_BOT_TOKEN", "PRICE_AGENT_TELEGRAM_CHAT_ID"),
            "email_smtp": _status(
                selected, "PRICE_AGENT_SMTP_HOST", "PRICE_AGENT_SMTP_USER",
                "PRICE_AGENT_SMTP_PASSWORD", "PRICE_AGENT_EMAIL_FROM",
                "PRICE_AGENT_EMAIL_TO"),
        },
        "network_checks_performed": 0,
        "secrets_returned": False,
        "note": "Configured means present, not tested or valid. No credentials are shown.",
    }
