"""Exact money normalization for provider-reported offers.

Only USD and INR are accepted; prices are stored in integer minor units.
No FX conversion is performed and currency provenance may not be inferred.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

SUPPORTED_CURRENCIES = frozenset({"INR", "USD"})
_MAX_MINOR = 10**12
_CURRENCY_MARKERS = {"INR": ("₹", "INR"), "USD": ("$", "USD")}
_PLAIN = re.compile(r"\d+(?:\.\d{1,2})?\Z")
_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?\Z")
_INDIAN_GROUPED = re.compile(r"\d{1,3}(?:,\d{2})+,\d{3}(?:\.\d{1,2})?\Z")


def validate_currency(currency: str) -> str:
    if not isinstance(currency, str) or currency.upper() not in SUPPORTED_CURRENCIES:
        raise ValueError("Explicit supported currency (INR or USD) required")
    return currency.upper()


def minor_units(value: str | int | Decimal, currency: str) -> int:
    """Parse an exact nonzero amount without floating-point threshold errors."""
    validate_currency(currency)
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("Price must be an integer, decimal, or decimal string")
    raw = str(value).strip()
    if isinstance(value, str):
        if not (_PLAIN.fullmatch(raw) or _GROUPED.fullmatch(raw)
                or (currency.upper() == "INR" and _INDIAN_GROUPED.fullmatch(raw))):
            raise ValueError("Invalid amount, grouping or precision")
    try:
        amount = Decimal(raw.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal price") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Price must be positive and finite")
    minor = amount * 100
    if minor != minor.to_integral_value() or minor > _MAX_MINOR:
        raise ValueError("Price exceeds allowed precision or range")
    return int(minor)


def provider_price(label: str, extracted: object) -> tuple[int, str]:
    """Require a provider price label with an *explicit* monetary currency."""
    if not isinstance(label, str) or len(label) > 80:
        raise ValueError("Provider price label missing or too long")
    match = re.fullmatch(r"\\s*(₹|INR|\\$|USD)\\s*([0-9][0-9,.]*)\\s*", label, flags=re.IGNORECASE)
    if not match:
        raise ValueError("Provider price must specify one unambiguous leading currency")
    symbol = match.group(1).upper()
    currency = "INR" if symbol in {"₹", "INR"} else "USD"
    value = match.group(2)
    cents = minor_units(value, currency)
    if extracted is not None:
        if isinstance(extracted, bool) or not isinstance(extracted, (int, float, str, Decimal)):
            raise ValueError("Invalid provider extracted_price")
        other = minor_units(str(extracted), currency)
        if cents != other:
            raise ValueError("Provider display and extracted prices disagree")
    return cents, currency


def format_minor(value: int, currency: str) -> str:
    currency = validate_currency(currency)
    if type(value) is not int or value < 0:
        raise ValueError("Invalid minor-unit amount")
    symbol = "₹" if currency == "INR" else "$"
    return f"{symbol}{value // 100:,}.{value % 100:02d}"
