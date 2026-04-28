from datetime import date
from decimal import Decimal

from services.cbr import CurrencyRate, RatesSnapshot
from services.formatter import format_rates


def test_formatter_output_matches_required_shape() -> None:
    snapshot = RatesSnapshot(
        date=date(2026, 4, 26),
        rates={
            "USD": CurrencyRate(
                code="USD",
                name="Доллар США",
                nominal=1,
                value=Decimal("75.5273"),
                unit_rate=Decimal("75.5273"),
                date=date(2026, 4, 26),
            ),
            "EUR": CurrencyRate(
                code="EUR",
                name="Евро",
                nominal=1,
                value=Decimal("88.2826"),
                unit_rate=Decimal("88.2826"),
                date=date(2026, 4, 26),
            ),
        },
        previous_date=date(2026, 4, 25),
        deltas={
            "USD": Decimal("0.69"),
            "EUR": Decimal("0.76"),
        },
    )

    assert format_rates(snapshot, ["USD", "EUR"]) == (
        "Курсы ЦБ РФ на 26.04.2026:\n"
        "\n"
        "Курс USD к RUB:\n"
        "1 Доллар США = 75,5273 (+0,69) руб.\n"
        "\n"
        "Курс EUR к RUB:\n"
        "1 Евро = 88,2826 (+0,76) руб."
    )
