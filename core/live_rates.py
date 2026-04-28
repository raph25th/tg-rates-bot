from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class LiveRatesError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveRate:
    code: str
    rub_rate: Decimal
    source: str


class InvestingLiveRatesProvider:
    source_name = "Investing"

    async def get_rate(self, code: str) -> LiveRate:
        # TODO: Реализовать получение live-курсов Investing для @rub_rates_bot.
        raise NotImplementedError("Investing live rates are not implemented yet")
