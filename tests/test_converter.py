from datetime import date
from decimal import Decimal

from core.models import CurrencyRate, RatesSnapshot
from services.converter import (
    convert_currency,
    format_calculator_result,
    format_conversion,
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
        },
    )


def test_parse_convert_request_ignores_case() -> None:
    request = parse_convert_request("10000 usd")

    assert request is not None
    assert request.amount == Decimal("10000")
    assert request.from_code == "USD"
    assert request.to_code == "RUB"


def test_parse_convert_request_accepts_comma_decimal() -> None:
    request = parse_convert_request("250,5 eur")

    assert request is not None
    assert request.amount == Decimal("250.5")
    assert request.from_code == "EUR"
    assert request.to_code == "RUB"


def test_parse_convert_request_accepts_grouped_rub_to_usd() -> None:
    request = parse_convert_request("1 000 000 rub usd")

    assert request is not None
    assert request.amount == Decimal("1000000")
    assert request.from_code == "RUB"
    assert request.to_code == "USD"


def test_parse_convert_request_rejects_invalid_text() -> None:
    assert parse_convert_request("hello") is None
    assert parse_convert_request("-100 usd") is None
    assert parse_convert_request("100 usd usd") is None


def test_convert_currency_to_rub() -> None:
    request = parse_convert_request("10000 usd")
    assert request is not None

    result = convert_currency(request, make_snapshot())

    assert result is not None
    assert result.result == Decimal("755273.0000")


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
        "Курс: 1 USD = 75,5273 ₽\n"
        "Дата курса: 25.04.2026\n"
        "Источник: ЦБ РФ\n"
        "\n"
        "Сформировано через @kurs_rub_bot"
    )


def test_format_conversion_keeps_legacy_shape() -> None:
    assert (
        format_conversion(
            amount=Decimal("100"),
            code="usd",
            result_rub=Decimal("7552.73"),
        )
        == "100 USD = 7 552,73 RUB"
    )
