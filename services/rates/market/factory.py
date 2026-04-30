from __future__ import annotations

from config import Settings
from services.rates.market.cache import CachedMarketRateProvider
from services.rates.market.disabled import DisabledMarketRateProvider
from services.rates.market.investing_apify import InvestingApifyProvider
from services.rates.market.investing_rapidapi import InvestingRapidApiProvider
from services.rates.market.investing_scraper import InvestingScraperProvider
from services.rates.market.mock import MockMarketRateProvider
from services.rates.market.yahoo import YahooMarketRateProvider


def build_market_rate_provider(app_config: Settings):
    mode = (app_config.market_rate_provider or app_config.investing_provider_mode or "disabled").strip().lower()
    if mode == "yahoo":
        provider = YahooMarketRateProvider(app_config)
    elif mode == "mock":
        provider = MockMarketRateProvider(app_config)
    elif mode == "investing_rapidapi":
        provider = InvestingRapidApiProvider(app_config)
    elif mode == "investing_apify":
        provider = InvestingApifyProvider(app_config)
    elif mode == "investing_scraper":
        provider = InvestingScraperProvider(app_config)
    else:
        provider = DisabledMarketRateProvider()
    return CachedMarketRateProvider(provider, app_config, ttl_seconds=60)
