from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_plain_amount, format_rate
from services.conversion_parser import (
    RUB_CODE,
    SUPPORTED_CURRENCIES,
    ConversionRequest,
    is_supported_conversion_request,
    is_supported_currency,
    looks_like_convert_attempt,
    parse_conversion_request,
)

SUPPORTED_CALCULATOR_CURRENCIES = SUPPORTED_CURRENCIES
DEFAULT_CBR_SOURCE = "ЦБ РФ — официальный курс"
MARKET_RATE_NOTICE = "Рыночный курс является ориентиром и может отличаться от банков, обменников и торговых платформ."


@dataclass(frozen=True)
class ConvertRequest:
    amount: Decimal
    from_code: str
    to_code: str = RUB_CODE
    percent: Decimal | None = None
    extra_payment_amount: Decimal | None = None
    direction: str = "currency_to_rub"

    @property
    def code(self) -> str:
        return self.from_code

    @property
    def is_reverse(self) -> bool:
        return self.direction == "rub_to_currency"


@dataclass(frozen=True)
class ConversionResult:
    request: ConvertRequest
    result: Decimal
    rate: CurrencyRate
    adjusted_unit_rate: Decimal
    main_payment_rub: Decimal | None = None
    extra_payment_amount: Decimal | None = None
    extra_payment_rub: Decimal | None = None
    final_result: Decimal | None = None
    source: str = DEFAULT_CBR_SOURCE

    @property
    def result_rub(self) -> Decimal:
        return self.result if self.request.to_code == RUB_CODE else self.request.amount


def parse_convert_request(text: str) -> ConvertRequest | None:
    parsed = parse_conversion_request(text)
    if parsed is None:
        return None
    return convert_parser_request(parsed)


def convert_parser_request(request: ConversionRequest) -> ConvertRequest:
    return ConvertRequest(
        amount=request.amount,
        from_code=request.from_currency,
        to_code=request.to_currency,
        percent=request.percent_adjustment,
        extra_payment_amount=request.extra_payment_amount,
        direction=request.direction,
    )


def is_supported_request(request: ConvertRequest) -> bool:
    return is_supported_conversion_request(
        ConversionRequest(
            amount=request.amount,
            from_currency=request.from_code,
            to_currency=request.to_code,
            percent_adjustment=request.percent,
            extra_payment_amount=request.extra_payment_amount,
            direction=request.direction,
        )
    )


def apply_percent(unit_rate: Decimal, percent: Decimal | None) -> Decimal:
    if percent is None:
        return unit_rate
    return unit_rate * (Decimal("1") + percent / Decimal("100"))


def convert_currency(
    request: ConvertRequest,
    snapshot: RatesSnapshot,
    source: str = DEFAULT_CBR_SOURCE,
) -> ConversionResult | None:
    if request.direction == "rub_to_currency":
        if request.extra_payment_amount is not None:
            return None
        rate = snapshot.rates.get(request.to_code)
        if rate is None:
            return None
        adjusted_rate = apply_percent(rate.unit_rate, request.percent)
        result_amount = request.amount / adjusted_rate
        return ConversionResult(
            request=request,
            result=result_amount,
            rate=rate,
            adjusted_unit_rate=adjusted_rate,
            final_result=result_amount,
            source=source,
        )

    rate = snapshot.rates.get(request.from_code)
    if rate is None:
        return None

    adjusted_rate = apply_percent(rate.unit_rate, request.percent)
    main_payment_rub = request.amount * adjusted_rate
    extra_payment_amount = request.extra_payment_amount
    extra_payment_rub = extra_payment_amount * adjusted_rate if extra_payment_amount is not None else None
    final_result = main_payment_rub + (extra_payment_rub or Decimal("0"))
    return ConversionResult(
        request=request,
        result=final_result,
        rate=rate,
        adjusted_unit_rate=adjusted_rate,
        main_payment_rub=main_payment_rub,
        extra_payment_amount=extra_payment_amount,
        extra_payment_rub=extra_payment_rub,
        final_result=final_result,
        source=source,
    )


def format_percent(percent: Decimal) -> str:
    sign = "+" if percent >= 0 else ""
    text = format(percent.normalize(), "f").replace(".", ",")
    return f"{sign}{text}%"


def format_rub(value: Decimal) -> str:
    return f"{format_number(value, places=2, trim_zero_fraction=False)} RUB"


def format_currency_amount(value: Decimal, code: str) -> str:
    if code == RUB_CODE:
        return format_rub(value)
    return f"{format_number(value, places=2, trim_zero_fraction=False)} {code}"


def format_input_amount(request: ConvertRequest) -> str:
    if request.from_code == RUB_CODE:
        return f"{format_plain_amount(request.amount)} RUB"
    return f"{format_plain_amount(request.amount)} {request.from_code}"


def format_extra_payment_amount(result: ConversionResult) -> str:
    amount = result.extra_payment_amount or Decimal("0")
    return f"{format_plain_amount(amount)} {result.rate.code}"


def has_extra_payment(result: ConversionResult) -> bool:
    return (
        result.request.direction == "currency_to_rub"
        and result.extra_payment_amount is not None
        and result.extra_payment_rub is not None
        and result.main_payment_rub is not None
    )


def format_calculator_title(source: str) -> str:
    if "цб" in source.casefold():
        return "💱 Расчёт по курсу ЦБ РФ"
    return "💱 Расчёт по рыночному курсу"


def format_calculator_result(result: ConversionResult) -> str:
    request = result.request
    rate = result.rate
    lines = [
        format_calculator_title(result.source),
        "",
        "Сумма:",
        format_input_amount(request),
        "",
        "Курс:",
        f"1 {rate.code} = {format_rate(rate.unit_rate)} RUB",
    ]

    if request.percent is not None:
        lines.extend(
            [
                "",
                "Корректировка:",
                format_percent(request.percent),
                "",
                "Расчётный курс:",
                f"1 {rate.code} = {format_rate(result.adjusted_unit_rate)} RUB",
            ]
        )

    if has_extra_payment(result):
        lines.extend(
            [
                "",
                "Основной платёж:",
                f"{format_input_amount(request)} = {format_rub(result.main_payment_rub or Decimal('0'))}",
                "",
                "Доп. платёж:",
                f"{format_extra_payment_amount(result)} = {format_rub(result.extra_payment_rub or Decimal('0'))}",
            ]
        )

    total_title = "Итого:"
    lines.extend(
        [
            "",
            total_title,
            format_currency_amount(result.result, request.to_code),
            "",
            "Дата курса:",
            rate.date.strftime("%d.%m.%Y"),
        ]
    )
    return "\n".join(lines)


def format_client_calculation_text(result: ConversionResult) -> str:
    request = result.request
    rate = result.rate
    title = "Расчёт валюты:" if request.direction == "rub_to_currency" else "Расчёт стоимости:"
    lines = [
        title,
        "",
        f"Сумма: {format_input_amount(request)}",
        f"Актуальный курс: 1 {rate.code} = {format_rate(rate.unit_rate)} RUB",
    ]

    if request.percent is not None:
        lines.append(f"Ставка: {format_percent(request.percent)}")
        if result.adjusted_unit_rate != rate.unit_rate:
            lines.append(f"Расчётный курс: 1 {rate.code} = {format_rate(result.adjusted_unit_rate)} RUB")

    if has_extra_payment(result):
        main_payment = result.main_payment_rub or Decimal("0")
        extra_payment = result.extra_payment_rub or Decimal("0")
        lines.extend(
            [
                "",
                "Основной платёж:",
                f"{format_input_amount(request)} = {format_rub(main_payment)}",
                "",
                "Доп. платёж:",
                f"{format_extra_payment_amount(result)} = {format_rub(extra_payment)}",
                "",
                "Итого:",
                f"{format_rub(main_payment)} + {format_rub(extra_payment)} = {format_rub(result.result)}",
            ]
        )
    else:
        lines.extend(
            [
                "",
                f"Итого: {format_currency_amount(result.result, request.to_code)}",
            ]
        )
    return "\n".join(lines)


def format_conversion(amount: Decimal, code: str, result_rub: Decimal) -> str:
    return f"{format_plain_amount(amount)} {code.upper()} = {format_number(result_rub)} RUB"
