from __future__ import annotations

from services.rates.market.base import INVESTING_UNAVAILABLE_TEXT, MarketRate, MarketRateProviderError


class DisabledMarketRateProvider:
    source = "INVESTING_DISABLED"

    async def get_rate(self, code: str) -> MarketRate:
        raise MarketRateProviderError(INVESTING_UNAVAILABLE_TEXT)

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        raise MarketRateProviderError(INVESTING_UNAVAILABLE_TEXT)
