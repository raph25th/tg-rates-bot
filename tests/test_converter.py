from datetime import date
from decimal import Decimal

from core.models import CurrencyRate, RatesSnapshot
from services.converter import (
    convert_currency,
    format_calculator_result,
    is_supported_currency,
    parse_convert_request,
)


def make_snapshot() -> RatesSnapshot:
    rate_date = date(2026, 4, 25)
    return RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate(
                code="USD",
                name="Доллар США",
                nominal=1,
                value=Decimal("75.5273"),
                unit_rate=Decimal("75.5273"),
                date=rate_date,
            ),
            "EUR": CurrencyRate(
                code="EUR",
                name="Евро",
                nominal=1,
                value=Decimal("88.2826"),
                unit_rate=Decimal("88.2826"),
                date=rate_date,
            ),
            "CNY": CurrencyRate(
                code="CNY",
                name="Китайский юань",
                nominal=10,
                value=Decimal("104.7000"),
                unit_rate=Decimal("10.4700"),
                date=rate_date,
            ),
        },
    )


def test_parse_100_usd() -> None:
    request = parse_convert_request("100 usd")

    assert request is not None
    assert request.amount == Decimal("100")
    assert request.code == "USD"


def test_parse_grouped_amount_ignores_currency_case() -> None:
    request = parse_convert_request("1 000 EUR")

    assert request is not None
    assert request.amount == Decimal("1000")
    assert request.code == "EUR"


def test_unknown_currency() -> None:
    request = parse_convert_request("100 gbp")

    assert request is not None
    assert request.code == "GBP"
    assert not is_supported_currency(request.code)


def test_convert_currency_to_rub() -> None:
    request = parse_convert_request("10000 usd")
    assert request is not None

    result = convert_currency(request, make_snapshot())

    assert result is not None
    assert result.result_rub == Decimal("755273.0000")


def test_format_calculator_result() -> None:
    request = parse_convert_request("10000 usd")
    assert request is not None
    result = convert_currency(request, make_snapshot())
    assert result is not None

    assert format_calculator_result(result) == (
        "💱 Расчёт валюты\n"
        "\n"
        "10 000 USD по курсу ЦБ РФ:\n"
        "= 755 273 ₽\n"
        "\n"
        "Курс:\n"
        "1 USD = 75,5273 ₽\n"
        "\n"
        "Дата курса:\n"
        "25.04.2026\n"
        "\n"
        "—\n"
        "\n"
        "Сформировано через @kurs_rub_bot"
    )
