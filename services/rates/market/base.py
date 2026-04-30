from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

MARKET_RATE_ORDER: tuple[str, ...] = ("USD", "EUR", "CNY", "GBP", "AED", "THB", "KRW", "JPY")
SUPPORTED_MARKET_PAIRS: dict[str, str] = {code: f"{code}/RUB" for code in MARKET_RATE_ORDER}
INVESTING_UNAVAILABLE_TEXT = "Курсы Investing временно недоступны. Проверьте настройки источника."


@dataclass(frozen=True)
class MarketRate:
    code: str
    pair: str
    value: Decimal
    source: str
    fetched_at: datetime


class MarketRateProviderError(RuntimeError):
    user_message = INVESTING_UNAVAILABLE_TEXT

    def __init__(self, message: str = INVESTING_UNAVAILABLE_TEXT) -> None:
        super().__init__(message)
        self.user_message = message


class PairUnavailableError(MarketRateProviderError):
    def __init__(self, pair: str) -> None:
        self.pair = pair
        super().__init__(f"Пара {pair} временно недоступна в Investing.")


class MarketRateProvider(Protocol):
    source: str

    async def get_rate(self, code: str) -> MarketRate:
        ...

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        ...


def pair_for_code(code: str) -> str:
    upper_code = code.upper()
    pair = SUPPORTED_MARKET_PAIRS.get(upper_code)
    if pair is None:
        raise PairUnavailableError(f"{upper_code}/RUB")
    return pair
