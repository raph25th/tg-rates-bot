from datetime import date
from decimal import Decimal

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_rate
from services.converter import (
    convert_currency,
    format_calculator_result,
    is_supported_request,
    looks_like_convert_attempt,
    parse_convert_request,
)


def make_snapshot() -> RatesSnapshot:
    rate_date = date(2026, 4, 30)
    return RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate(
                code="USD",
                name="Доллар США",
                nominal=1,
                value=Decimal("74.8806"),
                unit_rate=Decimal("74.8806"),
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
    assert request.from_code == "USD"
    assert request.to_code == "RUB"


def test_parse_grouped_amount_ignores_currency_case() -> None:
    request = parse_convert_request("1 000 EUR")

    assert request is not None
    assert request.amount == Decimal("1000")
    assert request.from_code == "EUR"
    assert request.to_code == "RUB"


def test_parse_reverse_rub_to_usd() -> None:
    request = parse_convert_request("1 000 000 rub usd")

    assert request is not None
    assert request.amount == Decimal("1000000")
    assert request.from_code == "RUB"
    assert request.to_code == "USD"


def test_parse_percent_without_sign_is_plus() -> None:
    request = parse_convert_request("10000 usd 2%")

    assert request is not None
    assert request.amount == Decimal("10000")
    assert request.from_code == "USD"
    assert request.to_code == "RUB"
    assert request.percent == Decimal("2")


def test_parse_positive_percent() -> None:
    request = parse_convert_request("10000 usd +2%")

    assert request is not None
    assert request.percent == Decimal("2")


def test_parse_negative_percent_with_dot() -> None:
    request = parse_convert_request("10000 usd -1.5%")

    assert request is not None
    assert request.percent == Decimal("-1.5")


def test_parse_grouped_eur_with_positive_percent() -> None:
    request = parse_convert_request("10 000 eur +3%")

    assert request is not None
    assert request.amount == Decimal("10000")
    assert request.from_code == "EUR"
    assert request.percent == Decimal("3")


def test_parse_percent_with_comma() -> None:
    request = parse_convert_request("100000 cny -0,5%")

    assert request is not None
    assert request.amount == Decimal("100000")
    assert request.from_code == "CNY"
    assert request.percent == Decimal("-0.5")


def test_invalid_format() -> None:
    assert parse_convert_request("hello") is None
    assert parse_convert_request("100") is None
    assert parse_convert_request("-100 usd") is None
    assert looks_like_convert_attempt("100") is True
    assert looks_like_convert_attempt("hello") is False


def test_format_number_helpers() -> None:
    assert format_number(Decimal("748806"), places=2, trim_zero_fraction=False) == "748 806,00"
    assert format_number(Decimal("13354.5889"), places=2, trim_zero_fraction=False) == "13 354,59"
    assert format_rate(Decimal("74.88056")) == "74,8806"


def test_convert_currency_to_rub() -> None:
    request = parse_convert_request("10000 usd")
    assert request is not None
    assert is_supported_request(request)

    result = convert_currency(request, make_snapshot())

    assert result is not None
    assert result.result == Decimal("748806.0000")


def test_convert_currency_to_rub_with_percent() -> None:
    request = parse_convert_request("10000 usd 2%")
    assert request is not None
    assert is_supported_request(request)

    result = convert_currency(request, make_snapshot())

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("76.378212")
    assert result.result == Decimal("763782.120000")


def test_convert_currency_to_rub_with_negative_percent() -> None:
    request = parse_convert_request("10000 usd -1.5%")
    assert request is not None
    assert is_supported_request(request)

    result = convert_currency(request, make_snapshot())

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("73.7573910")
    assert result.result == Decimal("737573.910000")


def test_convert_rub_to_currency() -> None:
    request = parse_convert_request("1 000 000 rub usd")
    assert request is not None
    assert is_supported_request(request)

    result = convert_currency(request, make_snapshot())

    assert result is not None
    assert result.result.quantize(Decimal("0.01")) == Decimal("13354.59")


def test_format_calculator_result_to_rub() -> None:
    request = parse_convert_request("10000 usd")
    assert request is not None
    result = convert_currency(request, make_snapshot())
    assert result is not None

    assert format_calculator_result(result) == (
        "💱 Расчёт валюты\n"
        "\n"
        "Сумма:\n"
        "10 000 USD\n"
        "\n"
        "Курс ЦБ РФ:\n"
        "1 USD = 74,8806 ₽\n"
        "\n"
        "Итого:\n"
        "748 806,00 ₽\n"
        "\n"
        "Дата курса:\n"
        "30.04.2026\n"
        "\n"
        "—\n"
        "Сформировано через @kurs_rub_bot"
    )


def test_format_calculator_result_with_percent() -> None:
    request = parse_convert_request("10000 usd +2%")
    assert request is not None
    result = convert_currency(request, make_snapshot())
    assert result is not None

    assert format_calculator_result(result) == (
        "💱 Расчёт валюты\n"
        "\n"
        "Сумма:\n"
        "10 000 USD\n"
        "\n"
        "Курс ЦБ РФ:\n"
        "1 USD = 74,8806 ₽\n"
        "\n"
        "Корректировка:\n"
        "+2%\n"
        "\n"
        "Расчётный курс:\n"
        "1 USD = 76,3782 ₽\n"
        "\n"
        "Итого:\n"
        "763 782,12 ₽\n"
        "\n"
        "Дата курса:\n"
        "30.04.2026\n"
        "\n"
        "—\n"
        "Сформировано через @kurs_rub_bot"
    )


def test_format_calculator_result_from_rub() -> None:
    request = parse_convert_request("1 000 000 rub usd")
    assert request is not None
    result = convert_currency(request, make_snapshot())
    assert result is not None

    assert format_calculator_result(result) == (
        "💱 Расчёт валюты\n"
        "\n"
        "Сумма:\n"
        "1 000 000 ₽\n"
        "\n"
        "Курс ЦБ РФ:\n"
        "1 USD = 74,8806 ₽\n"
        "\n"
        "Итого:\n"
        "13 354,59 USD\n"
        "\n"
        "Дата курса:\n"
        "30.04.2026\n"
        "\n"
        "—\n"
        "Сформировано через @kurs_rub_bot"
    )
