from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_plain_amount, format_rate

SUPPORTED_CALCULATOR_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "CNY")
RUB_CODE = "RUB"

_CONVERT_RE = re.compile(
    r"^\s*(?P<amount>\d+(?:[\s_]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s+(?P<from>[a-zA-Z]{3})(?:\s+(?P<to>[a-zA-Z]{3}))?"
    r"(?:\s+(?P<percent>[+-]?\d+(?:[.,]\d+)?)%)?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConvertRequest:
    amount: Decimal
    from_code: str
    to_code: str = RUB_CODE
    percent: Decimal | None = None

    @property
    def code(self) -> str:
        return self.from_code

    @property
    def is_reverse(self) -> bool:
        return self.from_code == RUB_CODE


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
    match = _CONVERT_RE.match(text)
    if match is None:
        return None

    amount_text = match.group("amount").replace(" ", "").replace("_", "").replace(",", ".")
    try:
        amount = Decimal(amount_text)
    except InvalidOperation:
        return None

    if amount <= 0:
        return None

    percent = parse_percent(match.group("percent"))
    if match.group("percent") is not None and percent is None:
        return None

    from_code = match.group("from").upper()
    to_code = (match.group("to") or RUB_CODE).upper()
    if from_code == to_code:
        return None

    return ConvertRequest(
        amount=amount,
        from_code=from_code,
        to_code=to_code,
        percent=percent,
    )


def parse_percent(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def looks_like_convert_attempt(text: str) -> bool:
    text = text.strip()
    if not text:
        return False

    if any(char.isdigit() for char in text):
        return True

    return re.search(r"\b[a-zA-Z]{3}\b", text) is not None


def is_supported_currency(code: str) -> bool:
    return code.upper() in SUPPORTED_CALCULATOR_CURRENCIES


def is_supported_request(request: ConvertRequest) -> bool:
    if request.from_code == RUB_CODE:
        return is_supported_currency(request.to_code)
    return request.to_code == RUB_CODE and is_supported_currency(request.from_code)


def apply_percent(unit_rate: Decimal, percent: Decimal | None) -> Decimal:
    if percent is None:
        return unit_rate
    return unit_rate * (Decimal("1") + percent / Decimal("100"))


def convert_currency(request: ConvertRequest, snapshot: RatesSnapshot) -> ConversionResult | None:
    if request.from_code == RUB_CODE:
        rate = snapshot.rates.get(request.to_code)
        if rate is None:
            return None
        adjusted_rate = apply_percent(rate.unit_rate, request.percent)
        return ConversionResult(
            request=request,
            result=request.amount / adjusted_rate,
            rate=rate,
            adjusted_unit_rate=adjusted_rate,
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
        "Сумма:",
        format_input_amount(request),
        "",
        "Курс ЦБ РФ:",
        f"1 {rate.code} = {format_rate(rate.unit_rate)} ₽",
    ]

    if request.percent is not None:
        lines.extend(
            [
                "",
                "Корректировка:",
                format_percent(request.percent),
                "",
                "Расчётный курс:",
                f"1 {rate.code} = {format_rate(result.adjusted_unit_rate)} ₽",
            ]
        )

    lines.extend(
        [
            "",
            "Итого:",
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
