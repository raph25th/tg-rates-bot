from datetime import datetime
from decimal import Decimal

import pytest

from config import Settings
from handlers.converter import market_rate_to_snapshot
from services.converter import convert_currency, parse_convert_request
from services.rates.market import MARKET_RATE_ORDER, MarketRateProviderError, build_market_rate_provider
from services.rates.market.base import INVESTING_UNAVAILABLE_TEXT
from services.rates.market.cache import CachedMarketRateProvider
from services.rates.market.investing_rapidapi import InvestingRapidApiProvider
from services.rates.market.mock import MockMarketRateProvider


def make_settings(**kwargs) -> Settings:
    values = {"bot_token": "123:test", "timezone": "Europe/Moscow"}
    values.update(kwargs)
    return Settings(**values)


@pytest.mark.asyncio
async def test_mock_provider_returns_market_rates() -> None:
    provider = build_market_rate_provider(make_settings(market_rate_provider="mock"))

    rates = await provider.get_rates(list(MARKET_RATE_ORDER))

    assert rates["USD"].pair == "USD/RUB"
    assert rates["USD"].value == Decimal("75.1200")
    assert rates["USD"].source == "Investing"


@pytest.mark.asyncio
async def test_disabled_provider_shows_safe_error() -> None:
    provider = build_market_rate_provider(make_settings(market_rate_provider="disabled"))

    with pytest.raises(MarketRateProviderError) as exc:
        await provider.get_rate("USD")

    assert str(exc.value) == INVESTING_UNAVAILABLE_TEXT


@pytest.mark.asyncio
async def test_rapidapi_without_key_does_not_crash() -> None:
    provider = InvestingRapidApiProvider(make_settings(investing_rapidapi_key=""))

    with pytest.raises(MarketRateProviderError) as exc:
        await provider.get_rate("USD")

    assert str(exc.value) == INVESTING_UNAVAILABLE_TEXT


@pytest.mark.asyncio
async def test_market_rate_cache_uses_ttl() -> None:
    base_provider = MockMarketRateProvider(make_settings())
    provider = CachedMarketRateProvider(base_provider, make_settings(), ttl_seconds=60)

    first = await provider.get_rate("USD")
    second = await provider.get_rate("USD")

    assert first == second
    assert base_provider.calls == 1


def test_conversion_with_market_snapshot_uses_market_value() -> None:
    request = parse_convert_request("100 usd")
    assert request is not None
    from services.rates.market.base import MarketRate

    market_rate = MarketRate(
        code="USD",
        pair="USD/RUB",
        value=Decimal("80.0000"),
        source="Investing",
        fetched_at=datetime(2026, 4, 30, 14, 35),
    )

    result = convert_currency(request, market_rate_to_snapshot(market_rate), source="Investing")

    assert result is not None
    assert result.rate.unit_rate == Decimal("80.0000")
    assert result.result == Decimal("8000.0000")
    assert result.source == "Investing"
