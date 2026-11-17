"""Explicit model-facing outcomes; never let INR rupees and paisa be confused."""
from __future__ import annotations
from dataclasses import dataclass
from typing import assert_never
from .models import Observation, Paisa, Status


def format_paisa(value: Paisa | None) -> str | None:
    if value is None:
        return None
    if value < 0:
        raise ValueError('Negative prices are invalid')
    rupees, subunit = divmod(value, 100)
    if rupees < 1000:
        grouped = str(rupees)
    else:
        head, tail = divmod(rupees, 1000)
        groups: list[str] = []
        while head >= 100:
            head, chunk = divmod(head, 100)
            groups.insert(0, f'{chunk:02d}')
        groups.insert(0, str(head))
        grouped = ','.join((*groups, f'{tail:03d}'))
    return f'₹{grouped}.{subunit:02d}'


@dataclass(frozen=True, slots=True)
class PriceToolResult:
    ok: bool
    error: str | None
    retryable: bool
    listing_id: str
    status: str
    price_paisa: Paisa | None
    price_display: str | None
    observed_utc: str | None
    retry_after_seconds: float | None

    @classmethod
    def from_observation(cls, listing_id: str, observation: Observation | None) -> PriceToolResult:
        if observation is None:
            return cls(False,'NO_APPROVED_SOURCE',False,listing_id,'UNAVAILABLE',None,None,None,None)
        status = observation.status
        match status:
            case Status.VALID_PRICE:
                ok, error, retryable = (observation.identity_verified and observation.price_paisa is not None), None, False
                if not ok:
                    error='INVALID_OBSERVATION'
            case Status.OUT_OF_STOCK:
                ok,error,retryable = False,'OUT_OF_STOCK',False
            case Status.QUARANTINED:
                ok,error,retryable = False,'QUARANTINED',False
            case Status.DOM_CHANGED:
                ok,error,retryable = False,'DOM_CHANGED',False
            case Status.API_THROTTLED:
                ok,error,retryable = False,'API_THROTTLED',True
            case Status.ACCESS_DENIED:
                ok,error,retryable = False,'ACCESS_DENIED',False
            case Status.TRANSIENT_ERROR:
                ok,error,retryable = False,'TRANSIENT_ERROR',True
            case Status.UNAVAILABLE:
                ok,error,retryable = False,'UNAVAILABLE',False
            case Status.DEFERRED:
                ok,error,retryable = False,'DEFERRED',True
            case _:
                assert_never(status)
        price = observation.price_paisa if ok else None
        return cls(bool(ok),error,retryable,listing_id,status.value,price,
                   format_paisa(price),observation.observed_utc,
                   observation.retry_after_seconds)

    def to_dict(self) -> dict[str, object]:
        return {
            'ok':self.ok,'error':self.error,'retryable':self.retryable,
            'listing_id':self.listing_id,'status':self.status,
            'price_paisa':self.price_paisa,'price_display':self.price_display,
            'observed_utc':self.observed_utc,'retry_after_seconds':self.retry_after_seconds,
        }
