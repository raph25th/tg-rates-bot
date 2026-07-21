from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_rate
from services.converter import (
    MaxInvoiceRequest,
    calculate_max_invoice,
    convert_agent_calculation,
    convert_currency,
    format_agent_calculation_result,
    format_calculator_result,
    format_client_calculation_text,
    format_max_invoice_result,
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
    assert result.adjusted_unit_rate == Decimal("77.5680")
    assert result.adjusted_extra_payment_unit_rate == Decimal("75.0000")
    assert result.invoice_base_rub == Decimal("750000.0000")
    assert result.cross_rate == Decimal("75.7500")
    assert result.main_currency_payment_rub == Decimal("775680.0000")
    assert result.extra_payment_rub == Decimal("7500.0000")
    assert result.main_payment_rub == Decimal("775680.0000")
    assert result.agent_fee_rub == Decimal("775.68000")
    assert result.final_result == Decimal("776455.68000")


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
    assert result.adjusted_unit_rate == Decimal("11.2575")
    assert result.adjusted_extra_payment_unit_rate == Decimal("10.9500")
    assert result.invoice_base_rub == Decimal("549690.0000")
    assert result.extra_payment_rub == Decimal("2190.0000")
    assert result.cross_rate == Decimal("10.99362549800796812749003984")
    assert result.main_currency_payment_rub == Decimal("565126.5000")
    assert result.main_payment_rub == Decimal("565126.5000")
    assert result.agent_fee_rub == Decimal("565.12650")
    assert result.final_result == Decimal("565691.62650")


def test_calculate_max_invoice_without_extra_payment_matches_limit() -> None:
    rate_date = date(2026, 7, 8)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "AED": CurrencyRate("AED", "Дирхам ОАЭ", 1, Decimal("21.3250"), Decimal("21.3250"), rate_date),
        },
    )
    request = MaxInvoiceRequest(
        limit_rub=Decimal("5000000"),
        invoice_code="AED",
        percent=Decimal("2.7"),
    )

    result = calculate_max_invoice(request, snapshot)

    assert result is not None
    assert result.main_rate_percent == Decimal("2.6")
    assert result.adjusted_unit_rate == Decimal("21.8795")
    assert result.max_invoice_amount == Decimal("228296.12")
    assert result.main_payment_rub == Decimal("4995004.957540")
    assert result.agent_fee_rub == Decimal("4995.004957540")
    assert result.final_result == Decimal("4999999.962497540")
    assert result.remainder_rub == Decimal("0.037502460")

    next_invoice_amount = result.max_invoice_amount + Decimal("0.01")
    next_main_payment = next_invoice_amount * result.adjusted_unit_rate
    next_total = next_main_payment + next_main_payment * result.agent_fee_percent / Decimal("100")
    assert next_total > request.limit_rub

    formatted = format_max_invoice_result(result)
    assert "Максимальная сумма инвойса на 08.07.2026" in formatted
    assert "Лимит клиента:\n5 000 000,00 RUB" in formatted
    assert "2,7% = 2,6% + 0,1%" in formatted
    assert "21,3250 + 2,6% = 21,8795 RUB" in formatted
    assert "Максимальная сумма инвойса:\n228 296,12 AED" in formatted
    assert "228 296,12 AED × 21,8795 = 4 995 004,96 RUB" in formatted
    assert "Итоговая сумма:\n4 999 999,96 RUB" in formatted
    assert "Остаток от лимита:\n0,04 RUB" in formatted


def test_calculate_max_invoice_with_extra_payment_in_other_currency() -> None:
    rate_date = date(2026, 7, 8)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "EUR": CurrencyRate("EUR", "Евро", 1, Decimal("88.0000"), Decimal("88.0000"), rate_date),
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    request = MaxInvoiceRequest(
        limit_rub=Decimal("500000"),
        invoice_code="EUR",
        percent=Decimal("2"),
        extra_payment_amount=Decimal("215"),
        extra_payment_code="USD",
    )

    result = calculate_max_invoice(request, snapshot)

    assert result is not None
    assert result.extra_payment_rate is not None
    assert result.extra_payment_rate.code == "USD"
    assert result.extra_payment_rub == Decimal("16125.0000")
    assert result.max_invoice_amount == Decimal("5387.06")
    assert result.cross_rate == Decimal("90.99328390624941990621971910")
    assert result.adjusted_unit_rate == Decimal("92.7222")
    assert result.main_payment_rub == Decimal("499500.054732")
    assert result.agent_fee_rub == Decimal("499.500054732")
    assert result.final_result == Decimal("499999.554786732")
    assert result.remainder_rub == Decimal("0.445213268")

    next_invoice_amount = result.max_invoice_amount + Decimal("0.01")
    next_invoice_base_rub = next_invoice_amount * result.rate.unit_rate
    next_cross_rate = (next_invoice_base_rub + result.extra_payment_rub) / next_invoice_amount
    next_adjusted_rate = next_cross_rate * (Decimal("1") + result.main_rate_percent / Decimal("100"))
    next_adjusted_rate = next_adjusted_rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    next_main_payment = next_invoice_amount * next_adjusted_rate
    next_total = next_main_payment + next_main_payment * result.agent_fee_percent / Decimal("100")
    assert next_total > request.limit_rub


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
    assert "Курс для расчёта ПП:\n1 USD = 76,1258 RUB" in formatted
    assert "Кросс-курс с учётом 100 USD:" in formatted
    assert "45 250 USD × 76,1258 = 3 444 692,45 RUB" in formatted
    assert "100 USD × 76,1258 = 7 612,58 RUB" in formatted
    assert "100 USD × 77,9528 = 7 795,28 RUB" not in formatted
    assert "(3 444 692,45 RUB + 7 612,58 RUB) / 45 250 USD = 76,2940 RUB" in formatted
    assert "Расчётный курс:\n76,2940 + 2,4% = 78,1251 RUB" in formatted
    assert result.adjusted_unit_rate == Decimal("78.1251")
    assert result.main_payment_rub == Decimal("3535160.7750")
    assert result.agent_fee_rub == Decimal("3535.160775")
    assert result.final_result == Decimal("3538695.935775")
    assert "45 250 USD × 78,1251 = 3 535 160,78 RUB" in formatted
    assert "3 535 347,44 RUB" not in formatted
    assert "3 535 160,78 RUB × 0,1% = 3 535,16 RUB" in formatted
    assert "Итоговая сумма:\n3 538 695,94 RUB" in formatted


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
    assert "Курс для расчёта ПП:\n1 USD = 75,0000 RUB" in formatted
    assert "Кросс-курс с учётом 100 USD:" in formatted
    assert "10 000 USD × 75,0000 = 750 000,00 RUB" in formatted
    assert "100 USD × 75,0000 = 7 500,00 RUB" in formatted
    assert "(750 000,00 RUB + 7 500,00 RUB) / 10 000 USD = 75,7500 RUB" in formatted
    assert "Расчётный курс:\n75,7500 + 2,4% = 77,5680 RUB" in formatted
    assert "10 000 USD × 77,5680 = 775 680,00 RUB" in formatted
    assert "Итого основной платёж:\n775 680,00 RUB" in formatted
    assert "775 680,00 RUB × 0,1% = 775,68 RUB" in formatted
    assert "Итоговая сумма:\n776 455,68 RUB" in formatted
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
    assert "Курс для расчёта ПП:\n1 CNY = 10,9500 RUB" in formatted
    assert "Кросс-курс с учётом 200 CNY:" in formatted
    assert "50 200 CNY × 10,9500 = 549 690,00 RUB" in formatted
    assert "200 CNY × 10,9500 = 2 190,00 RUB" in formatted
    assert "(549 690,00 RUB + 2 190,00 RUB) / 50 200 CNY = 10,9936 RUB" in formatted
    assert "Расчётный курс:\n10,9936 + 2,4% = 11,2575 RUB" in formatted
    assert "50 200 CNY × 11,2575 = 565 126,50 RUB" in formatted
    assert "Итого основной платёж:\n565 126,50 RUB" in formatted
    assert "565 126,50 RUB × 0,1% = 565,13 RUB" in formatted
    assert "Итоговая сумма:\n565 691,63 RUB" in formatted
    assert "Платёжка" not in formatted
    assert "Корректировка" not in formatted
    assert "Источник" not in formatted
