from __future__ import annotations

from config import Settings
from services.rates.market.base import INVESTING_UNAVAILABLE_TEXT, MarketRate, MarketRateProviderError


class InvestingApifyProvider:
    source = "Investing"

    def __init__(self, app_config: Settings) -> None:
        self.app_config = app_config

    async def get_rate(self, code: str) -> MarketRate:
        self._ensure_configured()
        raise MarketRateProviderError(INVESTING_UNAVAILABLE_TEXT)

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        self._ensure_configured()
        raise MarketRateProviderError(INVESTING_UNAVAILABLE_TEXT)

    def _ensure_configured(self) -> None:
        if not self.app_config.investing_apify_token:
            raise MarketRateProviderError(INVESTING_UNAVAILABLE_TEXT)
        # TODO: подключить Apify actor/task для получения live-курсов Investing.com.
