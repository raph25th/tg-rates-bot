from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import Settings
from services.cbr import CBRService
from services.rates.base import Rate


class CBRRateSource:
    source = "CBR"

    def __init__(self, cbr_service: CBRService, app_config: Settings) -> None:
        self.cbr_service = cbr_service
        self.app_config = app_config

    async def get_rates(self) -> dict[str, Rate]:
        timezone = ZoneInfo(self.app_config.timezone)
        fetched_at = datetime.now(timezone)
        snapshot = await self.cbr_service.fetch_rates(fetched_at.date())
        return {
            code: Rate(
                code=rate.code,
                name=rate.name,
                nominal=rate.nominal,
                value=rate.value,
                unit_rate=rate.unit_rate,
                date=rate.date,
                source=self.source,
                fetched_at=fetched_at,
            )
            for code, rate in snapshot.rates.items()
        }

    async def get_rate(self, currency_code: str) -> Rate | None:
        rates = await self.get_rates()
        return rates.get(currency_code.upper())
