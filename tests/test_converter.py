from datetime import date
from decimal import Decimal

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_rate
from services.converter import convert_currency, format_calculator_result, parse_convert_request


def make_snapshot() -> RatesSnapshot:
    rate_date = date(2026, 4, 30)
    return RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("74.8806"), Decimal("74.8806"), rate_date),
            "EUR": CurrencyRate("EUR", "Евро", 1, Decimal("88.2826"), Decimal("88.2826"), rate_date),
            "CNY": CurrencyRate("CNY", "Китайский юань", 10, Decimal("104.7000"), Decimal("10.4700"), rate_date),
            "AED": CurrencyRate("AED", "Дирхам ОАЭ", 1, Decimal("20.5656"), Decimal("20.5656"), rate_date),
            "THB": CurrencyRate("THB", "Таиландский бат", 10, Decimal("226.5000"), Decimal("22.6500"), rate_date),
            "KRW": CurrencyRate("KRW", "Вона Республики Корея", 1000, Decimal("54.3200"), Decimal("0.05432"), rate_date),
            "JPY": CurrencyRate("JPY", "Японская иена", 100, Decimal("48.9100"), Decimal("0.4891"), rate_date),
        },
    )


def test_format_number_helpers() -> None:
    assert format_number(Decimal("748806"), places=2, trim_zero_fraction=False) == "748 806,00"
    assert format_number(Decimal("13354.5889"), places=2, trim_zero_fraction=False) == "13 354,59"
    assert format_rate(Decimal("74.88056")) == "74,8806"


def test_convert_currency_to_rub() -> None:
    request = parse_convert_request("10000 usd")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")

    assert result is not None
    assert result.result == Decimal("748806.0000")


def test_convert_currency_to_rub_with_percent_and_direction_word() -> None:
    request = parse_convert_request("10 000 usd в руб +2%")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("76.378212")
    assert result.result == Decimal("763782.120000")


def test_convert_rub_to_currency() -> None:
    request = parse_convert_request("56 548 468 рублей в usd")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")

    assert result is not None
    assert result.result.quantize(Decimal("0.01")) == Decimal("755181.82")


def test_convert_rub_to_currency_with_negative_percent() -> None:
    request = parse_convert_request("56548468 rub в usd -1.5%")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("73.7573910")
    assert result.result.quantize(Decimal("0.01")) == Decimal("766682.05")


def test_convert_aed_to_rub_with_percent() -> None:
    request = parse_convert_request("10000 aed в руб +3%")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("21.182568")
    assert result.result == Decimal("211825.680000")


def test_convert_krw_uses_unit_rate_not_nominal_value() -> None:
    request = parse_convert_request("1000000 krw")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")

    assert result is not None
    assert result.rate.nominal == 1000
    assert result.rate.value == Decimal("54.3200")
    assert result.rate.unit_rate == Decimal("0.05432")
    assert result.result == Decimal("54320.00000")


def test_convert_jpy_uses_unit_rate_not_nominal_value() -> None:
    request = parse_convert_request("500000 jpy")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")

    assert result is not None
    assert result.rate.nominal == 100
    assert result.rate.value == Decimal("48.9100")
    assert result.rate.unit_rate == Decimal("0.4891")
    assert result.result == Decimal("244550.0000")


def test_format_calculator_result_to_rub_with_percent() -> None:
    request = parse_convert_request("10 000 USD в руб +2%")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")
    assert result is not None

    assert format_calculator_result(result) == (
        "💱 Расчёт валюты\n"
        "\n"
        "Источник:\n"
        "ЦБ РФ\n"
        "\n"
        "Сумма:\n"
        "10 000 USD\n"
        "\n"
        "Курс:\n"
        "1 USD = 74,8806 ₽\n"
        "\n"
        "Корректировка к курсу:\n"
        "+2%\n"
        "\n"
        "Расчётный курс:\n"
        "1 USD = 76,3782 ₽\n"
        "\n"
        "Итого к оплате:\n"
        "763 782,12 ₽\n"
        "\n"
        "Дата курса:\n"
        "30.04.2026\n"
        "\n"
        "—\n"
        "Сформировано через @kurs_rub_bot"
    )


def test_format_calculator_result_from_rub() -> None:
    request = parse_convert_request("1 000 000 ₽ в eur")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="ЦБ РФ")
    assert result is not None

    assert format_calculator_result(result) == (
        "💱 Расчёт валюты\n"
        "\n"
        "Источник:\n"
        "ЦБ РФ\n"
        "\n"
        "Сумма:\n"
        "1 000 000 ₽\n"
        "\n"
        "Курс:\n"
        "1 EUR = 88,2826 ₽\n"
        "\n"
        "Итого:\n"
        "11 327,26 EUR\n"
        "\n"
        "Дата курса:\n"
        "30.04.2026\n"
        "\n"
        "—\n"
        "Сформировано через @kurs_rub_bot"
    )
