from datetime import datetime
from decimal import Decimal

import pytest

from config import Settings
from handlers.converter import market_rate_to_snapshot
from services.converter import convert_currency, parse_convert_request
from services.rates.market import MARKET_RATE_ORDER, MarketRateProviderError, build_market_rate_provider
from services.rates.market.base import MARKET_UNAVAILABLE_TEXT, MOCK_MARKET_SOURCE, MOCK_MARKET_WARNING, YAHOO_MARKET_SOURCE
from services.rates.market.cache import CachedMarketRateProvider
from services.rates.market.formatter import format_market_rates
from services.rates.market.investing_rapidapi import InvestingRapidApiProvider
from services.rates.market.mock import MockMarketRateProvider
from services.rates.market.yahoo import YahooMarketRateProvider, _extract_fast_info_price


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
    assert rates["USD"].source == MOCK_MARKET_SOURCE


def test_factory_selects_yahoo_provider() -> None:
    provider = build_market_rate_provider(make_settings(market_rate_provider="yahoo"))

    assert provider.source == YAHOO_MARKET_SOURCE
    assert isinstance(provider.provider, YahooMarketRateProvider)
    assert not isinstance(provider.provider, MockMarketRateProvider)


@pytest.mark.asyncio
async def test_mock_rates_are_marked_as_test_mode() -> None:
    provider = build_market_rate_provider(make_settings(market_rate_provider="mock"))

    rates = await provider.get_rates(["USD"])
    message = format_market_rates(rates, ("USD",))

    assert "📈 Рыночный курс" in message
    assert f"Источник: {MOCK_MARKET_SOURCE}" in message
    assert MOCK_MARKET_WARNING in message


@pytest.mark.asyncio
async def test_disabled_provider_shows_safe_error() -> None:
    provider = build_market_rate_provider(make_settings(market_rate_provider="disabled"))

    with pytest.raises(MarketRateProviderError) as exc:
        await provider.get_rate("USD")

    assert str(exc.value) == MARKET_UNAVAILABLE_TEXT


@pytest.mark.asyncio
async def test_rapidapi_without_key_does_not_crash() -> None:
    provider = InvestingRapidApiProvider(make_settings(investing_rapidapi_key=""))

    with pytest.raises(MarketRateProviderError) as exc:
        await provider.get_rate("USD")

    assert str(exc.value) == MARKET_UNAVAILABLE_TEXT


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


def test_mock_conversion_can_show_mock_source() -> None:
    request = parse_convert_request("100 usd")
    assert request is not None
    from services.rates.market.base import MarketRate

    market_rate = MarketRate(
        code="USD",
        pair="USD/RUB",
        value=Decimal("80.0000"),
        source=MOCK_MARKET_SOURCE,
        fetched_at=datetime(2026, 4, 30, 14, 35),
    )

    result = convert_currency(request, market_rate_to_snapshot(market_rate), source=market_rate.source)

    assert result is not None
    assert result.source == MOCK_MARKET_SOURCE


@pytest.mark.asyncio
async def test_unavailable_yahoo_does_not_crash() -> None:
    class EmptyYahooProvider(YahooMarketRateProvider):
        async def _get_value(self, code: str):
            return None

    provider = EmptyYahooProvider(make_settings(market_rate_provider="yahoo"))

    with pytest.raises(MarketRateProviderError) as exc:
        await provider.get_rates(["USD"])

    assert str(exc.value) == MARKET_UNAVAILABLE_TEXT


def test_yahoo_reads_last_price_from_fast_info() -> None:
    price, field = _extract_fast_info_price({"lastPrice": 92.5})

    assert price == Decimal("92.5")
    assert field == "lastPrice"


def test_yahoo_uses_fast_info_fallback_fields() -> None:
    price, field = _extract_fast_info_price({"previousClose": 91.25})

    assert price == Decimal("91.25")
    assert field == "previousClose"


@pytest.mark.asyncio
async def test_yahoo_direct_ticker_uses_fast_info_last_price() -> None:
    class FakeTicker:
        fast_info = {"lastPrice": 93.75}

    provider = YahooMarketRateProvider(make_settings(market_rate_provider="yahoo"))
    provider._ticker_factory = lambda ticker: FakeTicker()

    rate = await provider.get_rate("USD")

    assert rate.pair == "USD/RUB"
    assert rate.source == YAHOO_MARKET_SOURCE
    assert rate.value == Decimal("93.75")


@pytest.mark.asyncio
async def test_yahoo_falls_back_through_usd_cross() -> None:
    class FakeTicker:
        def __init__(self, price):
            self.fast_info = {"lastPrice": price} if price is not None else {}

    prices = {
        "JPYRUB=X": None,
        "RUB=X": 90,
        "JPY=X": 150,
    }
    provider = YahooMarketRateProvider(make_settings(market_rate_provider="yahoo"))
    provider._ticker_factory = lambda ticker: FakeTicker(prices[ticker])

    rate = await provider.get_rate("JPY")

    assert rate.value == Decimal("0.6")
