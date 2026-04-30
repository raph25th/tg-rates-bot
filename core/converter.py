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


@dataclass(frozen=True)
class ConvertRequest:
    amount: Decimal
    from_code: str
    to_code: str = RUB_CODE
    percent: Decimal | None = None
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
    source: str = "ЦБ РФ"

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
        direction=request.direction,
    )


def is_supported_request(request: ConvertRequest) -> bool:
    return is_supported_conversion_request(
        ConversionRequest(
            amount=request.amount,
            from_currency=request.from_code,
            to_currency=request.to_code,
            percent_adjustment=request.percent,
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
    source: str = "ЦБ РФ",
) -> ConversionResult | None:
    if request.direction == "rub_to_currency":
        rate = snapshot.rates.get(request.to_code)
        if rate is None:
            return None
        adjusted_rate = apply_percent(rate.unit_rate, request.percent)
        return ConversionResult(
            request=request,
            result=request.amount / adjusted_rate,
            rate=rate,
            adjusted_unit_rate=adjusted_rate,
            source=source,
        )

    rate = snapshot.rates.get(request.from_code)
    if rate is None:
        return None

    adjusted_rate = apply_percent(rate.unit_rate, request.percent)
    return ConversionResult(
        request=request,
        result=request.amount * adjusted_rate,
        rate=rate,
        adjusted_unit_rate=adjusted_rate,
        source=source,
    )


def format_percent(percent: Decimal) -> str:
    sign = "+" if percent >= 0 else ""
    text = format(percent.normalize(), "f").replace(".", ",")
    return f"{sign}{text}%"


def format_rub(value: Decimal) -> str:
    return f"{format_number(value, places=2, trim_zero_fraction=False)} ₽"


def format_currency_amount(value: Decimal, code: str) -> str:
    if code == RUB_CODE:
        return format_rub(value)
    return f"{format_number(value, places=2, trim_zero_fraction=False)} {code}"


def format_input_amount(request: ConvertRequest) -> str:
    if request.from_code == RUB_CODE:
        return f"{format_plain_amount(request.amount)} ₽"
    return f"{format_plain_amount(request.amount)} {request.from_code}"


def format_calculator_result(result: ConversionResult) -> str:
    request = result.request
    rate = result.rate
    lines = [
        "💱 Расчёт валюты",
        "",
        "Источник:",
        result.source,
        "",
        "Сумма:",
        format_input_amount(request),
        "",
        "Курс:",
        f"1 {rate.code} = {format_rate(rate.unit_rate)} ₽",
    ]

    if request.percent is not None:
        lines.extend(
            [
                "",
                "Корректировка к курсу:",
                format_percent(request.percent),
                "",
                "Расчётный курс:",
                f"1 {rate.code} = {format_rate(result.adjusted_unit_rate)} ₽",
            ]
        )

    total_title = "Итого к оплате:" if request.direction == "currency_to_rub" else "Итого:"
    lines.extend(
        [
            "",
            total_title,
            format_currency_amount(result.result, request.to_code),
            "",
            "Дата курса:",
            rate.date.strftime("%d.%m.%Y"),
            "",
            "—",
            "Сформировано через @kurs_rub_bot",
        ]
    )
    return "\n".join(lines)


def format_conversion(amount: Decimal, code: str, result_rub: Decimal) -> str:
    return f"{format_plain_amount(amount)} {code.upper()} = {format_number(result_rub)} RUB"
