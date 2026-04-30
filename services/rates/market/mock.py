from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from config import Settings
from services.rates.market.base import MARKET_RATE_ORDER, MarketRate, PairUnavailableError, pair_for_code

MOCK_MARKET_RATES: dict[str, Decimal] = {
    "USD": Decimal("75.1200"),
    "EUR": Decimal("86.4300"),
    "CNY": Decimal("10.3600"),
    "GBP": Decimal("98.5100"),
    "AED": Decimal("20.4500"),
    "THB": Decimal("2.3000"),
    "KRW": Decimal("0.0550"),
    "JPY": Decimal("0.4900"),
}


class MockMarketRateProvider:
    source = "Investing"

    def __init__(self, app_config: Settings) -> None:
        self.app_config = app_config
        self.calls = 0

    async def get_rate(self, code: str) -> MarketRate:
        self.calls += 1
        upper_code = code.upper()
        value = MOCK_MARKET_RATES.get(upper_code)
        if value is None:
            raise PairUnavailableError(f"{upper_code}/RUB")
        return MarketRate(
            code=upper_code,
            pair=pair_for_code(upper_code),
            value=value,
            source=self.source,
            fetched_at=datetime.now(ZoneInfo(self.app_config.timezone)),
        )

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        return {code.upper(): await self.get_rate(code) for code in codes if code.upper() in MARKET_RATE_ORDER}
