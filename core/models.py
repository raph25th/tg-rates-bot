from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class CurrencyRate:
    code: str
    name: str
    nominal: int
    value: Decimal
    unit_rate: Decimal
    date: date


@dataclass(frozen=True)
class RatesSnapshot:
    date: date
    rates: dict[str, CurrencyRate]
    previous_date: date | None = None
    deltas: dict[str, Decimal] = field(default_factory=dict)

    def get(self, code: str) -> CurrencyRate | None:
        return self.rates.get(code.upper())
