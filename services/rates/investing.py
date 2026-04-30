from __future__ import annotations

from services.rates.base import Rate, RateSourceError

INVESTING_UNAVAILABLE_MESSAGE = (
    "📈 Рыночный курс\n"
    "\n"
    "Рыночные курсы временно недоступны.\n"
    "\n"
    "Попробуйте позже или используйте курс ЦБ РФ."
)


class InvestingUnavailableError(RateSourceError):
    pass


class InvestingRateSource:
    source = "INVESTING"

    async def get_rates(self) -> dict[str, Rate]:
        raise InvestingUnavailableError(
            "Рыночные курсы временно недоступны. Попробуйте позже или используйте курс ЦБ РФ."
        )

    async def get_rate(self, currency_code: str) -> Rate | None:
        raise InvestingUnavailableError(
            "Рыночные курсы временно недоступны. Попробуйте позже или используйте курс ЦБ РФ."
        )


def get_investing_unavailable_message() -> str:
    return INVESTING_UNAVAILABLE_MESSAGE
