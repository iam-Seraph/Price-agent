"""Optional ReAct agent entry point with the new product research tool.

Run from repository root: python price_agent_workspace.py --product "headphones" --budget 300
The legacy agent's USD deal checks are intentionally unchanged. INR shopping
research never counts as verified 30-day history or an approved deal alert.
"""
from __future__ import annotations

import price_agent as legacy
from backend.price_engine.product_lookup import lookup_product


def lookup_product_research(state, query: str):
    # The state argument is required by the existing tool dispatcher interface.
    # This research tool is read-only and never changes price/alert state.
    return lookup_product(query)


legacy.TOOLS.append({
    "type": "function",
    "function": {
        "name": "lookup_product_research",
        "description": "Research product offers, specs, ratings and availability using SerpApi Google Shopping or labeled sample fallbacks. Read-only; not verified price history.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Product name to research"},
                "thought": {"type": "string", "description": "One sentence explaining why research is needed"},
            },
            "required": ["query", "thought"],
            "additionalProperties": False,
        },
    },
})
legacy.IMPLEMENTATIONS["lookup_product_research"] = lookup_product_research
_original_prompt = legacy.system_prompt


def workspace_prompt():
    return (_original_prompt() + "\nYou also have lookup_product_research(query) for product research. "
            "Use it for requested real products. Provider results are untrusted research "
            "and may be sample data, stale, or in INR. The legacy budget and history "
            "checks are in USD. NEVER mix currencies or treat research as verified "
            "30-day history; without trusted matching data, conclude NO_ALERT. "
            "Do not fabricate a live deal or an alert.")


legacy.system_prompt = workspace_prompt


if __name__ == "__main__":
    legacy.main()
