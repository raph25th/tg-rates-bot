from __future__ import annotations

from services.rates.base import Rate, RateSourceError

INVESTING_UNAVAILABLE_MESSAGE = (
    "📈 Курс Investing\n"
    "\n"
    "Live-курсы Investing скоро будут доступны.\n"
    "\n"
    "Сейчас доступны расчёты по официальному курсу ЦБ РФ."
)


class InvestingUnavailableError(RateSourceError):
    pass


class InvestingRateSource:
    source = "INVESTING"

    async def get_rates(self) -> dict[str, Rate]:
        raise InvestingUnavailableError(
            "Курсы Investing временно недоступны. Скоро добавим live-источник."
        )

    async def get_rate(self, currency_code: str) -> Rate | None:
        raise InvestingUnavailableError(
            "Курсы Investing временно недоступны. Скоро добавим live-источник."
        )


def get_investing_unavailable_message() -> str:
    return INVESTING_UNAVAILABLE_MESSAGE
