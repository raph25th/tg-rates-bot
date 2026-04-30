from __future__ import annotations

import argparse
import asyncio
import logging
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

logger = logging.getLogger(__name__)

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

    def __init__(self, app_config: Settings) -> None:
        self.app_config = app_config
        self._ticker_factory = None

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
            return await asyncio.to_thread(self._fetch_ticker_value_sync, ticker)
        except Exception as exc:
            logger.warning("Yahoo ticker failed: %s; error: %s", ticker, exc)
            return None

    def _fetch_ticker_value_sync(self, ticker: str) -> Decimal | None:
        ticker_obj = self._make_ticker(ticker)
        price, field_name = _extract_fast_info_price(ticker_obj.fast_info)
        logger.info("Yahoo ticker requested: %s; field: %s; value: %s", ticker, field_name or "missing", price)
        return price

    def _make_ticker(self, ticker: str):
        if self._ticker_factory is not None:
            return self._ticker_factory(ticker)
        import yfinance as yf

        return yf.Ticker(ticker)


def _extract_fast_info_price(fast_info) -> tuple[Decimal | None, str | None]:
    fields = ("lastPrice", "regularMarketPrice", "previousClose", "regularMarketPreviousClose")
    try:
        info = dict(fast_info)
    except Exception:
        info = fast_info

    for field in fields:
        try:
            value = info.get(field)
        except AttributeError:
            value = None
        parsed = _to_decimal(value)
        if parsed is not None and parsed > 0:
            return parsed, field
    return None, None


def _to_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


async def _diagnose(code: str) -> int:
    settings = Settings(bot_token="diagnostic-token", market_rate_provider="yahoo")
    provider = YahooMarketRateProvider(settings)
    upper_code = code.upper()
    ticker = DIRECT_TICKERS.get(upper_code)
    if ticker is None:
        print(f"Unsupported code: {upper_code}")
        return 1

    print(f"ticker: {ticker}")
    print(f"source: {provider.source}")
    ticker_obj = provider._make_ticker(ticker)
    price, field = _extract_fast_info_price(ticker_obj.fast_info)
    print(f"{field or 'lastPrice'}: {price}")
    rate = await provider.get_rate(upper_code)
    print(f"MarketRate: {rate}")
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Diagnose Yahoo Finance market rate provider")
    parser.add_argument("code", help="Currency code, for example USD")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_diagnose(args.code)))


if __name__ == "__main__":
    main()
