from __future__ import annotations
import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Sequence
from .models import Observation, Status

# Strict INR grouping: 1,49,999.00, 999.00, 149999.00.
_INR = re.compile(r'^(?:₹\s*|INR\s*)?(?:([1-9]\d{0,2}(?:,\d{2})*,\d{3}|\d+))(?:\.(\d{1,2}))?$', re.I)
_FORBIDDEN = re.compile(r'\b(?:emi|monthly|month|mo|installment|instalment|coupon|cashback|exchange|up\s+to|starting\s+at|per\s+month)\b|/\s*(?:mo|month)', re.I)

def parse_inr_paisa(raw: str) -> int:
    if not isinstance(raw, str):
        raise TypeError('Price must be a string')
    value = raw.strip()
    if _FORBIDDEN.search(value):
        raise ValueError('Conditional or installment price')
    match = _INR.fullmatch(value)
    if not match:
        raise ValueError('Invalid INR amount or grouping')
    cleaned = re.sub(r'^(?:₹\s*|INR\s*)', '', value, flags=re.I).replace(',', '')
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError('Invalid decimal amount') from exc
    paisa = amount * 100
    if amount <= 0 or paisa != paisa.to_integral_value() or paisa > 10**12:
        raise ValueError('Invalid price range or precision')
    return int(paisa)

def validate_observation(obs: Observation, history: Sequence[int]) -> Observation:
    if obs.status == Status.OUT_OF_STOCK:
        if obs.price_paisa is not None:
            return replace(obs, status=Status.QUARANTINED, reason='OUT_OF_STOCK_WITH_PRICE')
        return obs
    if obs.status != Status.VALID_PRICE:
        return obs
    if not obs.identity_verified:
        return replace(obs, status=Status.QUARANTINED, reason='IDENTITY_UNVERIFIED')
    if obs.currency != 'INR' or obs.price_paisa is None or obs.availability != 'IN_STOCK':
        return replace(obs, status=Status.QUARANTINED, reason='INVALID_PRICE_CURRENCY_OR_STOCK')
    if history:
        previous = history[-1]
        if obs.price_paisa * 2 < previous:
            return replace(obs, status=Status.QUARANTINED, reason='DROP_OVER_50_PERCENT')
        if obs.price_paisa > previous * 2:
            return replace(obs, status=Status.QUARANTINED, reason='INCREASE_OVER_100_PERCENT')
    if len(history) >= 10:
        med = median(history[-30:])
        if abs(obs.price_paisa - med) * 100 > med * 40:
            return replace(obs, status=Status.QUARANTINED, reason='MEDIAN_VARIANCE_OVER_40_PERCENT')
    return obs
