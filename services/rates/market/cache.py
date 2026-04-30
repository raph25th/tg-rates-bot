from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import Settings
from services.rates.market.base import MarketRate, MarketRateProvider


class CachedMarketRateProvider:
    def __init__(self, provider: MarketRateProvider, app_config: Settings, ttl_seconds: int = 60) -> None:
        self.provider = provider
        self.app_config = app_config
        self.ttl = timedelta(seconds=ttl_seconds)
        self.source = provider.source
        self._cache: dict[str, MarketRate] = {}
        self._expires_at: dict[str, datetime] = {}

    async def get_rate(self, code: str) -> MarketRate:
        upper_code = code.upper()
        now = self._now()
        cached = self._cache.get(upper_code)
        expires_at = self._expires_at.get(upper_code)
        if cached is not None and expires_at is not None and expires_at > now:
            return cached

        rate = await self.provider.get_rate(upper_code)
        self._cache[upper_code] = rate
        self._expires_at[upper_code] = now + self.ttl
        return rate

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        result: dict[str, MarketRate] = {}
        missing: list[str] = []
        now = self._now()
        for code in codes:
            upper_code = code.upper()
            cached = self._cache.get(upper_code)
            expires_at = self._expires_at.get(upper_code)
            if cached is not None and expires_at is not None and expires_at > now:
                result[upper_code] = cached
            else:
                missing.append(upper_code)

        if missing:
            fresh_rates = await self.provider.get_rates(missing)
            expires_at = now + self.ttl
            for code, rate in fresh_rates.items():
                upper_code = code.upper()
                self._cache[upper_code] = rate
                self._expires_at[upper_code] = expires_at
                result[upper_code] = rate

        return result

    def _now(self) -> datetime:
        return datetime.now(ZoneInfo(self.app_config.timezone))
