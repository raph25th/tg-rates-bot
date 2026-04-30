from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from config import Settings
from services.rates.market.base import (
    MARKET_UNAVAILABLE_TEXT,
    YAHOO_MARKET_SOURCE,
    MarketRate,
    MarketRateProviderError,
    PairUnavailableError,
    pair_for_code,
)

DIRECT_TICKERS: dict[str, str] = {
    "USD": "RUB=X",
    "EUR": "EURRUB=X",
    "CNY": "CNYRUB=X",
    "GBP": "GBPRUB=X",
    "AED": "AEDRUB=X",
    "THB": "THBRUB=X",
    "KRW": "KRWRUB=X",
    "JPY": "JPYRUB=X",
}

USD_CROSS_TICKERS: dict[str, str] = {
    "CNY": "CNY=X",
    "AED": "AED=X",
    "THB": "THB=X",
    "KRW": "KRW=X",
    "JPY": "JPY=X",
}


class YahooMarketRateProvider:
    source = YAHOO_MARKET_SOURCE
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart"

    def __init__(self, app_config: Settings, timeout_seconds: int = 10) -> None:
        self.app_config = app_config
        self.timeout_seconds = timeout_seconds

    async def get_rate(self, code: str) -> MarketRate:
        upper_code = code.upper()
        pair = pair_for_code(upper_code)
        value = await self._get_value(upper_code)
        if value is None:
            raise PairUnavailableError(pair)

        return MarketRate(
            code=upper_code,
            pair=pair,
            value=value,
            source=self.source,
            fetched_at=datetime.now(ZoneInfo(self.app_config.timezone)),
        )

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        result: dict[str, MarketRate] = {}
        for code in codes:
            try:
                rate = await self.get_rate(code)
            except PairUnavailableError:
                continue
            result[rate.code] = rate
        if not result:
            raise MarketRateProviderError(MARKET_UNAVAILABLE_TEXT)
        return result

    async def _get_value(self, code: str) -> Decimal | None:
        direct_ticker = DIRECT_TICKERS.get(code)
        if direct_ticker is None:
            return None

        direct_value = await self._fetch_ticker_value(direct_ticker)
        if direct_value is not None:
            return direct_value

        if code == "USD":
            return None

        usd_cross_ticker = USD_CROSS_TICKERS.get(code)
        if usd_cross_ticker is None:
            return None

        usd_rub = await self._fetch_ticker_value("RUB=X")
        usd_code = await self._fetch_ticker_value(usd_cross_ticker)
        if usd_rub is None or usd_code is None or usd_code == 0:
            return None
        return usd_rub / usd_code

    async def _fetch_ticker_value(self, ticker: str) -> Decimal | None:
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.base_url}/{ticker}",
                    params={"range": "1d", "interval": "1m"},
                ) as response:
                    response.raise_for_status()
                    payload = await response.json()
        except Exception as exc:
            raise MarketRateProviderError(MARKET_UNAVAILABLE_TEXT) from exc

        return _extract_chart_price(payload)


def _extract_chart_price(payload: dict) -> Decimal | None:
    try:
        result = payload["chart"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return None

    meta_price = result.get("meta", {}).get("regularMarketPrice")
    parsed_meta = _to_decimal(meta_price)
    if parsed_meta is not None and parsed_meta > 0:
        return parsed_meta

    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
    for close in reversed(closes):
        parsed_close = _to_decimal(close)
        if parsed_close is not None and parsed_close > 0:
            return parsed_close
    return None


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
