from datetime import date
from decimal import Decimal

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_rate
from services.converter import (
    convert_agent_calculation,
    convert_currency,
    format_agent_calculation_result,
    format_calculator_result,
    format_client_calculation_text,
    parse_convert_request,
)


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

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.result == Decimal("748806.0000")


def test_convert_currency_to_rub_with_percent_and_direction_word() -> None:
    request = parse_convert_request("10 000 usd в руб +2%")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("76.378212")
    assert result.result == Decimal("763782.120000")


def test_convert_currency_to_rub_with_extra_payment_and_percent() -> None:
    rate_date = date(2026, 5, 5)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = parse_convert_request("10000 usd +2% +100ПП")
    assert request is not None

    result = convert_currency(request, snapshot, source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("76.500000")
    assert result.main_payment_rub == Decimal("765000.000000")
    assert result.extra_payment_amount == Decimal("100")
    assert result.extra_payment_rub == Decimal("7650.000000")
    assert result.final_result == Decimal("772650.000000")
    assert result.result == Decimal("772650.000000")


def test_convert_currency_to_rub_with_extra_payment_in_usd_for_non_usd_currency() -> None:
    rate_date = date(2026, 5, 5)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
            "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("10.9500"), Decimal("10.9500"), rate_date),
        },
    )
    request = parse_convert_request("50200 cny +2% +200ПП")
    assert request is not None

    result = convert_currency(request, snapshot, source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("11.169000")
    assert result.adjusted_extra_payment_unit_rate == Decimal("76.500000")
    assert result.main_payment_rub == Decimal("560683.800000")
    assert result.extra_payment_amount == Decimal("200")
    assert result.extra_payment_rate is not None
    assert result.extra_payment_rate.code == "USD"
    assert result.extra_payment_rub == Decimal("15300.000000")
    assert result.final_result == Decimal("575983.800000")
    assert result.result == Decimal("575983.800000")


def test_agent_calculation_usd_without_extra_payment() -> None:
    rate_date = date(2026, 5, 15)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = parse_convert_request("10000 usd агент +2,5%")
    assert request is not None

    result = convert_agent_calculation(request, snapshot)

    assert result is not None
    assert result.main_rate_percent == Decimal("2.4")
    assert result.adjusted_unit_rate == Decimal("76.800000")
    assert result.main_payment_rub == Decimal("768000.000000")
    assert result.agent_fee_rub == Decimal("768.0000000")
    assert result.final_result == Decimal("768768.0000000")


def test_agent_calculation_usd_with_extra_payment() -> None:
    rate_date = date(2026, 5, 15)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = parse_convert_request("10000 usd агент +2,5% +100ПП")
    assert request is not None

    result = convert_agent_calculation(request, snapshot)

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("77.5864")
    assert result.adjusted_extra_payment_unit_rate == Decimal("76.8000")
    assert result.invoice_base_rub == Decimal("750000.0000")
    assert result.cross_rate == Decimal("75.7680000")
    assert result.main_currency_payment_rub == Decimal("775864.0000")
    assert result.extra_payment_rub == Decimal("7680.000000")
    assert result.main_payment_rub == Decimal("775864.0000")
    assert result.agent_fee_rub == Decimal("775.86400")
    assert result.final_result == Decimal("776639.86400")


def test_agent_calculation_cny_with_extra_payment() -> None:
    rate_date = date(2026, 5, 15)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
            "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("10.9500"), Decimal("10.9500"), rate_date),
        },
    )
    request = parse_convert_request("50200 cny агент +2,5% +200ПП")
    assert request is not None

    result = convert_agent_calculation(request, snapshot)

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("11.2585")
    assert result.adjusted_extra_payment_unit_rate == Decimal("11.2128")
    assert result.invoice_base_rub == Decimal("549690.0000")
    assert result.extra_payment_rub == Decimal("2242.5600")
    assert result.cross_rate == Decimal("10.99467250996015936254980080")
    assert result.main_currency_payment_rub == Decimal("565176.7000")
    assert result.main_payment_rub == Decimal("565176.7000")
    assert result.agent_fee_rub == Decimal("565.17670")
    assert result.final_result == Decimal("565741.87670")


def test_convert_rub_to_currency() -> None:
    request = parse_convert_request("56 548 468 рублей в usd")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.result.quantize(Decimal("0.01")) == Decimal("755181.82")


def test_convert_rub_to_currency_with_negative_percent() -> None:
    request = parse_convert_request("56548468 rub в usd -1.5%")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("73.7573910")
    assert result.result.quantize(Decimal("0.01")) == Decimal("766682.05")


def test_convert_aed_to_rub_with_percent() -> None:
    request = parse_convert_request("10000 aed в руб +3%")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.adjusted_unit_rate == Decimal("21.182568")
    assert result.result == Decimal("211825.680000")


def test_convert_krw_uses_unit_rate_not_nominal_value() -> None:
    request = parse_convert_request("1000000 krw")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.rate.nominal == 1000
    assert result.rate.value == Decimal("54.3200")
    assert result.rate.unit_rate == Decimal("0.05432")
    assert result.result == Decimal("54320.00000")


def test_convert_jpy_uses_unit_rate_not_nominal_value() -> None:
    request = parse_convert_request("500000 jpy")
    assert request is not None

    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")

    assert result is not None
    assert result.rate.nominal == 100
    assert result.rate.value == Decimal("48.9100")
    assert result.rate.unit_rate == Decimal("0.4891")
    assert result.result == Decimal("244550.0000")


def test_format_calculator_result_to_rub_with_percent() -> None:
    request = parse_convert_request("10 000 USD в руб +2%")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")
    assert result is not None

    assert format_calculator_result(result) == (
        "Расчёт стоимости:\n"
        "\n"
        "Сумма: 10 000 USD\n"
        "Актуальный курс: 1 USD = 74,8806 RUB\n"
        "Ставка: +2%\n"
        "Расчётный курс: 1 USD = 76,3782 RUB\n"
        "\n"
        "Итого: 763 782,12 RUB"
    )


def test_format_calculator_result_from_rub() -> None:
    request = parse_convert_request("1 000 000 ₽ в eur")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")
    assert result is not None

    assert format_calculator_result(result) == (
        "Расчёт валюты:\n"
        "\n"
        "Сумма: 1 000 000 RUB\n"
        "Актуальный курс: 1 EUR = 88,2826 RUB\n"
        "\n"
        "Итого: 11 327,26 EUR"
    )


def test_format_calculator_result_for_market_source_is_clean() -> None:
    request = parse_convert_request("100 USD")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="Yahoo Finance — рыночный ориентир")
    assert result is not None

    formatted = format_calculator_result(result)

    assert formatted == (
        "Расчёт стоимости:\n"
        "\n"
        "Сумма: 100 USD\n"
        "Актуальный курс: 1 USD = 74,8806 RUB\n"
        "\n"
        "Итого: 7 488,06 RUB"
    )
    assert "Источник:" not in formatted
    assert "Сформировано через @kurs_rub_bot" not in formatted
    assert "Рыночный курс является ориентиром" not in formatted
    assert "Итого: 7 488,06 RUB" in formatted
    assert "₽" not in formatted
    assert "Корректировка" not in formatted


def test_format_client_calculation_text_to_rub_with_percent_uses_rate_label() -> None:
    request = parse_convert_request("10 000 USD в руб +2%")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")
    assert result is not None

    formatted = format_client_calculation_text(result)

    assert formatted == (
        "Расчёт стоимости:\n"
        "\n"
        "Сумма: 10 000 USD\n"
        "Актуальный курс: 1 USD = 74,8806 RUB\n"
        "Ставка: +2%\n"
        "Расчётный курс: 1 USD = 76,3782 RUB\n"
        "\n"
        "Итого: 763 782,12 RUB"
    )
    assert "Сумма: 10 000 USD" in formatted
    assert "Сумма:10 000 USD" not in formatted
    assert "Ставка: +2%" in formatted
    assert "Ставка:+2%" not in formatted
    assert "Корректировка" not in formatted
    assert "₽" not in formatted


def test_format_client_calculation_text_without_percent_omits_rate_lines() -> None:
    request = parse_convert_request("10 000 USD")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")
    assert result is not None

    formatted = format_client_calculation_text(result)

    assert formatted == (
        "Расчёт стоимости:\n"
        "\n"
        "Сумма: 10 000 USD\n"
        "Актуальный курс: 1 USD = 74,8806 RUB\n"
        "\n"
        "Итого: 748 806,00 RUB"
    )
    assert "Ставка" not in formatted
    assert "Расчётный курс" not in formatted
    assert "Корректировка" not in formatted
    assert "Итого: 748 806,00 RUB" in formatted
    assert "₽" not in formatted


def test_format_client_calculation_text_from_rub_with_percent() -> None:
    request = parse_convert_request("1 000 000 ₽ в usd +2%")
    assert request is not None
    result = convert_currency(request, make_snapshot(), source="ЦБ РФ — официальный курс")
    assert result is not None

    formatted = format_client_calculation_text(result)

    assert formatted.startswith(
        "Расчёт валюты:\n"
        "\n"
        "Сумма: 1 000 000 RUB\n"
        "Актуальный курс: 1 USD = 74,8806 RUB\n"
        "Ставка: +2%\n"
        "Расчётный курс: 1 USD = 76,3782 RUB\n"
        "\n"
        "Итого: "
    )
    assert formatted.endswith(" USD")
    assert "Корректировка" not in formatted
    assert "₽" not in formatted


def test_format_client_calculation_text_with_extra_payment() -> None:
    rate_date = date(2026, 5, 5)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = parse_convert_request("10000 usd +2% +100ПП")
    assert request is not None
    result = convert_currency(request, snapshot, source="ЦБ РФ — официальный курс")
    assert result is not None

    formatted = format_client_calculation_text(result)

    assert formatted == (
        "Расчёт стоимости:\n"
        "\n"
        "Сумма: 10 000 USD\n"
        "Актуальный курс: 1 USD = 75,0000 RUB\n"
        "Ставка: +2%\n"
        "Расчётный курс: 1 USD = 76,5000 RUB\n"
        "\n"
        "Основной платёж:\n"
        "10 000 USD = 765 000,00 RUB\n"
        "\n"
        "Доп. платёж:\n"
        "100 USD = 7 650,00 RUB\n"
        "\n"
        "Итого:\n"
        "765 000,00 RUB + 7 650,00 RUB = 772 650,00 RUB"
    )
    assert "Доп. платёж" in formatted
    assert "Основной платёж" in formatted
    assert "Ставка: +2%" in formatted
    assert "ПП" not in formatted
    assert "Платёжка" not in formatted
    assert "Корректировка" not in formatted
    assert "₽" not in formatted


def test_format_client_calculation_text_with_extra_payment_in_usd_for_non_usd_currency() -> None:
    rate_date = date(2026, 5, 5)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
            "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("10.9500"), Decimal("10.9500"), rate_date),
        },
    )
    request = parse_convert_request("50200 CNY +2% +200ПП")
    assert request is not None
    result = convert_currency(request, snapshot, source="ЦБ РФ — официальный курс")
    assert result is not None

    formatted = format_client_calculation_text(result)

    assert formatted == (
        "Расчёт стоимости:\n"
        "\n"
        "Сумма: 50 200 CNY\n"
        "Актуальный курс: 1 CNY = 10,9500 RUB\n"
        "Ставка: +2%\n"
        "Расчётный курс: 1 CNY = 11,1690 RUB\n"
        "\n"
        "Основной платёж:\n"
        "50 200 CNY = 560 683,80 RUB\n"
        "\n"
        "Доп. платёж:\n"
        "200 USD × 76,5000 RUB = 15 300,00 RUB\n"
        "\n"
        "Итого:\n"
        "560 683,80 RUB + 15 300,00 RUB = 575 983,80 RUB"
    )
    assert "Доп. платёж" in formatted
    assert "ПП" not in formatted
    assert "Платёжка" not in formatted


def test_format_client_calculation_text_with_extra_payment_without_percent() -> None:
    rate_date = date(2026, 5, 5)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = parse_convert_request("10000 usd +100ПП")
    assert request is not None
    result = convert_currency(request, snapshot, source="ЦБ РФ — официальный курс")
    assert result is not None

    formatted = format_client_calculation_text(result)

    assert "Ставка" not in formatted
    assert "Расчётный курс" not in formatted
    assert "Основной платёж:\n10 000 USD = 750 000,00 RUB" in formatted
    assert "Доп. платёж:\n100 USD = 7 500,00 RUB" in formatted
    assert "750 000,00 RUB + 7 500,00 RUB = 757 500,00 RUB" in formatted


def test_format_agent_calculation_text_usd_without_extra_payment() -> None:
    rate_date = date(2026, 5, 15)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = parse_convert_request("10000 usd агент +2,5%")
    assert request is not None
    result = convert_agent_calculation(request, snapshot)
    assert result is not None

    formatted = format_agent_calculation_result(result)

    assert formatted == (
        "Агентский расчёт на 15.05.2026\n"
        "\n"
        "Актуальный курс:\n"
        "1 USD = 75,0000 RUB\n"
        "\n"
        "Сумма инвойса:\n"
        "10 000 USD\n"
        "\n"
        "Ставка клиенту:\n"
        "2,5% = 2,4% + 0,1%\n"
        "\n"
        "Расчётный курс:\n"
        "75,0000 + 2,4% = 76,8000 RUB\n"
        "\n"
        "Основной платёж:\n"
        "10 000 USD × 76,8000 = 768 000,00 RUB\n"
        "\n"
        "Агентское вознаграждение:\n"
        "768 000,00 RUB × 0,1% = 768,00 RUB\n"
        "\n"
        "Итого:\n"
        "Основной платёж: 768 000,00 RUB\n"
        "Агентское вознаграждение: 768,00 RUB\n"
        "\n"
        "Итоговая сумма:\n"
        "768 768,00 RUB"
    )
    assert "Дата курса:" not in formatted
    assert "Курс в поручении" not in formatted
    assert "Фиксированное ПП" not in formatted
    assert "ПП" not in formatted
    assert "Платёжка" not in formatted
    assert "Корректировка" not in formatted
    assert "₽" not in formatted


def test_format_agent_calculation_text_target_usd_without_extra_payment() -> None:
    rate_date = date(2026, 7, 8)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("76.1258"), Decimal("76.1258"), rate_date),
        },
    )
    request = parse_convert_request("45250 usd агент +2,5%")
    assert request is not None
    result = convert_agent_calculation(request, snapshot)
    assert result is not None

    formatted = format_agent_calculation_result(result)

    assert formatted == (
        "Агентский расчёт на 08.07.2026\n"
        "\n"
        "Актуальный курс:\n"
        "1 USD = 76,1258 RUB\n"
        "\n"
        "Сумма инвойса:\n"
        "45 250 USD\n"
        "\n"
        "Ставка клиенту:\n"
        "2,5% = 2,4% + 0,1%\n"
        "\n"
        "Расчётный курс:\n"
        "76,1258 + 2,4% = 77,9528 RUB\n"
        "\n"
        "Основной платёж:\n"
        "45 250 USD × 77,9528 = 3 527 364,20 RUB\n"
        "\n"
        "Агентское вознаграждение:\n"
        "3 527 364,20 RUB × 0,1% = 3 527,36 RUB\n"
        "\n"
        "Итого:\n"
        "Основной платёж: 3 527 364,20 RUB\n"
        "Агентское вознаграждение: 3 527,36 RUB\n"
        "\n"
        "Итоговая сумма:\n"
        "3 530 891,56 RUB"
    )
    assert "Курс для расчёта ПП" not in formatted
    assert "Кросс-курс" not in formatted


def test_format_agent_calculation_text_target_usd_with_extra_payment_cross_rate() -> None:
    rate_date = date(2026, 7, 8)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("76.1258"), Decimal("76.1258"), rate_date),
        },
    )
    request = parse_convert_request("45250 usd агент +2,5% +100ПП")
    assert request is not None
    result = convert_agent_calculation(request, snapshot)
    assert result is not None

    formatted = format_agent_calculation_result(result)

    assert "Агентский расчёт на 08.07.2026" in formatted
    assert "Сумма инвойса:\n45 250 USD" in formatted
    assert "Курс для расчёта ПП:\n76,1258 + 2,4% = 77,9528 RUB" in formatted
    assert "Кросс-курс с учётом 100 USD:" in formatted
    assert "45 250 USD × 76,1258 = 3 444 692,45 RUB" in formatted
    assert "100 USD × 77,9528 = 7 795,28 RUB" in formatted
    assert "(3 444 692,45 RUB + 7 795,28 RUB) / 45 250 USD = 76,2981 RUB" in formatted
    assert "Расчётный курс:\n76,2981 + 2,4% = 78,1292 RUB" in formatted
    assert result.adjusted_unit_rate == Decimal("78.1292")
    assert result.main_payment_rub == Decimal("3535346.3000")
    assert result.agent_fee_rub == Decimal("3535.34630")
    assert result.final_result == Decimal("3538881.64630")
    assert "45 250 USD × 78,1292 = 3 535 346,30 RUB" in formatted
    assert "3 535 347,44 RUB" not in formatted
    assert "3 535 346,30 RUB × 0,1% = 3 535,35 RUB" in formatted
    assert "Итоговая сумма:\n3 538 881,65 RUB" in formatted


def test_format_agent_calculation_text_usd_with_extra_payment() -> None:
    rate_date = date(2026, 5, 15)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = parse_convert_request("10000 usd агент +2,5% +100ПП")
    assert request is not None
    result = convert_agent_calculation(request, snapshot)
    assert result is not None

    formatted = format_agent_calculation_result(result)

    assert "2,5% + 100 USD = 2,4% + 0,1% + 100 USD" in formatted
    assert "Курс для расчёта ПП:\n75,0000 + 2,4% = 76,8000 RUB" in formatted
    assert "Кросс-курс с учётом 100 USD:" in formatted
    assert "10 000 USD × 75,0000 = 750 000,00 RUB" in formatted
    assert "100 USD × 76,8000 = 7 680,00 RUB" in formatted
    assert "(750 000,00 RUB + 7 680,00 RUB) / 10 000 USD = 75,7680 RUB" in formatted
    assert "Расчётный курс:\n75,7680 + 2,4% = 77,5864 RUB" in formatted
    assert "10 000 USD × 77,5864 = 775 864,00 RUB" in formatted
    assert "Итого основной платёж:\n775 864,00 RUB" in formatted
    assert "775 864,00 RUB × 0,1% = 775,86 RUB" in formatted
    assert "Итоговая сумма:\n776 639,86 RUB" in formatted
    assert "Платёжка" not in formatted


def test_format_agent_calculation_text_cny_with_extra_payment() -> None:
    rate_date = date(2026, 5, 15)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
            "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("10.9500"), Decimal("10.9500"), rate_date),
        },
    )
    request = parse_convert_request("50200 cny агент +2,5% +200ПП")
    assert request is not None
    result = convert_agent_calculation(request, snapshot)
    assert result is not None

    formatted = format_agent_calculation_result(result)

    assert "Агентский расчёт на 15.05.2026" in formatted
    assert "2,5% + 200 CNY = 2,4% + 0,1% + 200 CNY" in formatted
    assert "Курс для расчёта ПП:\n10,9500 + 2,4% = 11,2128 RUB" in formatted
    assert "Кросс-курс с учётом 200 CNY:" in formatted
    assert "50 200 CNY × 10,9500 = 549 690,00 RUB" in formatted
    assert "200 CNY × 11,2128 = 2 242,56 RUB" in formatted
    assert "(549 690,00 RUB + 2 242,56 RUB) / 50 200 CNY = 10,9947 RUB" in formatted
    assert "Расчётный курс:\n10,9947 + 2,4% = 11,2585 RUB" in formatted
    assert "50 200 CNY × 11,2585 = 565 176,70 RUB" in formatted
    assert "Итого основной платёж:\n565 176,70 RUB" in formatted
    assert "565 176,70 RUB × 0,1% = 565,18 RUB" in formatted
    assert "Итоговая сумма:\n565 741,88 RUB" in formatted
    assert "Платёжка" not in formatted
    assert "Корректировка" not in formatted
    assert "Источник" not in formatted
