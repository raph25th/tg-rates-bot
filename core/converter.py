from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_plain_amount, format_rate

SUPPORTED_CALCULATOR_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "CNY")

_CONVERT_RE = re.compile(
    r"^\s*(?P<amount>\d+(?:[\s_]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s+(?P<code>[a-zA-Z]{3})\s*$",
    re.IGNORECASE,
)
_CALC_ATTEMPT_RE = re.compile(r"\d|[a-zA-Z]{3}", re.IGNORECASE)


@dataclass(frozen=True)
class ConvertRequest:
    amount: Decimal
    code: str

    @property
    def from_code(self) -> str:
        return self.code

    @property
    def to_code(self) -> str:
        return "RUB"


@dataclass(frozen=True)
class ConversionResult:
    request: ConvertRequest
    result_rub: Decimal
    rate: CurrencyRate
    source: str = "ЦБ РФ"

    @property
    def result(self) -> Decimal:
        return self.result_rub


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

    return ConvertRequest(amount=amount, code=match.group("code").upper())


def looks_like_convert_attempt(text: str) -> bool:
    text = text.strip()
    if not text:
        return False

    has_digit = any(char.isdigit() for char in text)
    has_currency_like_word = re.search(r"\b[a-zA-Z]{2,5}\b", text) is not None
    return has_digit or (has_currency_like_word and bool(_CALC_ATTEMPT_RE.search(text)))


def is_supported_currency(code: str) -> bool:
    return code.upper() in SUPPORTED_CALCULATOR_CURRENCIES


def convert_currency(request: ConvertRequest, snapshot: RatesSnapshot) -> ConversionResult | None:
    rate = snapshot.rates.get(request.code)
    if rate is None:
        return None

    return ConversionResult(
        request=request,
        result_rub=request.amount * rate.unit_rate,
        rate=rate,
    )


def format_rub(value: Decimal) -> str:
    return f"{format_number(value, places=2)} ₽"


def format_calculator_result(result: ConversionResult) -> str:
    request = result.request
    rate = result.rate

    return "\n".join(
        [
            "💱 Расчёт валюты",
            "",
            f"{format_plain_amount(request.amount)} {request.code} по курсу {result.source}:",
            f"= {format_rub(result.result_rub)}",
            "",
            "Курс:",
            f"1 {rate.code} = {format_rate(rate.unit_rate)} ₽",
            "",
            "Дата курса:",
            rate.date.strftime("%d.%m.%Y"),
            "",
            "—",
            "",
            "Сформировано через @kurs_rub_bot",
        ]
    )


def format_conversion(amount: Decimal, code: str, result_rub: Decimal) -> str:
    return f"{format_plain_amount(amount)} {code.upper()} = {format_number(result_rub)} RUB"
