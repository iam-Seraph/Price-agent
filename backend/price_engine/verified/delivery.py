"""Lease-safe, opt-in delivery of already-qualified price alerts."""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from .alert_store import AlertStore
from .analysis import analyze_offer
from .money import format_minor
from .notifier import AlertConfigurationError, AlertDeliveryError, send_alert


def deliver_due(store: AlertStore, *, limit: int = 5,
                sender: Callable[[str, str], None] = send_alert) -> list[dict[str, Any]]:
    """Revalidate source evidence immediately before sending, never auto-buy."""
    records = store.claim_deliveries(limit=limit)
    results = []
    for item in records:
        code = ""
        retryable = False
        success = False
        try:
            with store.watches.prices.connect() as db:
                watch = db.execute("""
                    SELECT budget_minor,currency,enabled FROM verified_watch_queries
                    WHERE watch_id=?
                """, (item["watch_id"],)).fetchone()
            if watch is None or not watch["enabled"]:
                code = "WATCH_DISABLED"
            elif watch["currency"] != item["currency"]:
                code = "CURRENCY_CHANGED"
            else:
                budget = Decimal(int(watch["budget_minor"])) / Decimal(100)
                report = analyze_offer(store.watches.prices, str(item["offer_id"]), budget)
                if (report["decision"] != "ALERT"
                        or report["price_minor"] != item["price_minor"]):
                    code = "EVIDENCE_CHANGED"
                else:
                    product = str(report["name"]).replace("\r", " ").replace("\n", " ")[:200]
                    merchant = str(report["merchant"]).replace("\r", " ").replace("\n", " ")[:120]
                    message = (
                        "Price Agent threshold alert\n"
                        + "Product: " + product + "\n"
                        + "Merchant: " + merchant + "\n"
                        + "Provider-reported price: "
                        + format_minor(int(item["price_minor"]), str(item["currency"])) + "\n"
                        + "Your budget: " + report["budget"] + "\n"
                        + "Observed (UTC): " + str(report["last_observed_at"]) + "\n"
                        + "Evidence type: PROVIDER_REPORTED (not independently audited)\n"
                        + "Source URL: " + str(report["url"]) + "\n"
                        + "This alert is information only; no purchase has been made."
                    )
                    sender(str(item["channel"]), message)
                    success = True
        except AlertConfigurationError:
            code = "CHANNEL_NOT_CONFIGURED"
        except AlertDeliveryError:
            code = "PROVIDER_SEND_ERROR"
            retryable = True
        except (ValueError, TypeError, KeyError):
            code = "INVALID_STORED_EVIDENCE"
        status = store.complete_delivery(item, success=success,
                                         retryable=retryable, error_code=code)
        results.append({"delivery_id": item["delivery_id"], "status": status,
                        "channel": item["channel"], "error_code": code})
    return results
