"""Safe assistant actions limited to grounded local research or explicit watch creation."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from .commands import ShoppingIntent, parse_shopping_intent
from .comparison import comparison_table
from .explanations import explain_candidates
from .research import research_offers
from .store import VerifiedPriceStore
from .learning import LearningStore
from .watch_store import WatchStore


def plan_command(command: str) -> dict[str, object]:
    plan = parse_shopping_intent(command)
    return {
        "intent": plan.as_dict(),
        "side_effects": ["save_watch_rule"] if plan.action == "CREATE_WATCH" else [],
        "needs_explicit_confirmation": plan.requires_confirmation,
        "automatic_purchases": False,
        "network_requests": False,
        "notice": "Only saved provider prices can be compared. A watch requires a separate monitoring worker and opt-in alert channel.",
    }


def execute_command(db_path: str | Path, command: str, *,
                    confirmed: bool = False) -> dict[str, Any]:
    """Execute only commands in the explicit grammar; no shell or arbitrary tools."""
    if type(confirmed) is not bool:
        raise ValueError("Confirmation flag must be boolean")
    plan: ShoppingIntent = parse_shopping_intent(command)
    if plan.action == "CREATE_WATCH":
        if not confirmed:
            return {"status": "CONFIRMATION_REQUIRED", "plan": plan_command(command)}
        watch_id = WatchStore(db_path).add_watch(
            plan.query, str(Decimal(plan.budget_minor) / Decimal(100)),
            plan.currency, interval_minutes=60)
        return {"status": "WATCH_SAVED", "watch_id": watch_id,
                "polling_started": False, "notification_configured": False,
                "message": "Watch saved only. Start a monitor separately and opt in to an alert channel."}
    store = VerifiedPriceStore(db_path)
    budget = Decimal(plan.budget_minor) / Decimal(100)
    research = research_offers(store, plan.query, budget, currency=plan.currency, limit=30,
                               learning=LearningStore(db_path))
    return {
        "status": "RESEARCH_COMPLETED",
        "research": research,
        "comparison": comparison_table(research),
        "explanations": explain_candidates(research),
        "network_requests": False,
    }
