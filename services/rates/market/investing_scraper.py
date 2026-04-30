from __future__ import annotations

from config import Settings
from services.rates.market.base import INVESTING_UNAVAILABLE_TEXT, MarketRate, MarketRateProviderError


class InvestingScraperProvider:
    source = "Investing"

    def __init__(self, app_config: Settings) -> None:
        self.app_config = app_config

    async def get_rate(self, code: str) -> MarketRate:
        raise MarketRateProviderError(INVESTING_UNAVAILABLE_TEXT)

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        raise MarketRateProviderError(INVESTING_UNAVAILABLE_TEXT)
        # TODO: реализовать аккуратный scraper-адаптер с rate limits и устойчивым парсингом.
