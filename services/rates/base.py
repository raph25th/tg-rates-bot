from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


class RateSourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Rate:
    code: str
    name: str
    nominal: int
    value: Decimal
    unit_rate: Decimal
    date: date
    source: str
    fetched_at: datetime


class RateSource(Protocol):
    source: str

    async def get_rates(self) -> dict[str, Rate]:
        raise NotImplementedError

    async def get_rate(self, currency_code: str) -> Rate | None:
        raise NotImplementedError
