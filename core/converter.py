from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_money, format_number, format_plain_amount, format_rate

SUPPORTED_CALCULATOR_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "CNY", "GBP")
SUPPORTED_INPUT_CURRENCIES: tuple[str, ...] = ("RUB",) + SUPPORTED_CALCULATOR_CURRENCIES

_CONVERT_RE = re.compile(
    r"^\s*(?P<amount>\d+(?:[\s_]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s+(?P<from>[a-zA-Z]{3})(?:\s+(?P<to>[a-zA-Z]{3}))?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConvertRequest:
    amount: Decimal
    from_code: str
    to_code: str = "RUB"

    @property
    def code(self) -> str:
        return self.from_code


@dataclass(frozen=True)
class ConversionResult:
    request: ConvertRequest
    result: Decimal
    rate: CurrencyRate
    source: str = "ЦБ РФ"


def parse_convert_request(text: str) -> ConvertRequest | None:
    match = _CONVERT_RE.match(text)
    if match is None:
        return None

    try:
        amount = Decimal(match.group("amount").replace(" ", "").replace("_", "").replace(",", "."))
    except InvalidOperation:
        return None

    if amount <= 0:
        return None

    from_code = match.group("from").upper()
    to_code = (match.group("to") or "RUB").upper()
    if from_code not in SUPPORTED_INPUT_CURRENCIES or to_code not in SUPPORTED_INPUT_CURRENCIES:
        return None
    if from_code == to_code:
        return None

    return ConvertRequest(amount=amount, from_code=from_code, to_code=to_code)


def convert_currency(request: ConvertRequest, snapshot: RatesSnapshot) -> ConversionResult | None:
    if request.from_code == "RUB":
        rate = snapshot.rates.get(request.to_code)
        if rate is None:
            return None
        return ConversionResult(request=request, result=request.amount / rate.unit_rate, rate=rate)

    from_rate = snapshot.rates.get(request.from_code)
    if from_rate is None:
        return None

    if request.to_code == "RUB":
        return ConversionResult(
            request=request,
            result=request.amount * from_rate.unit_rate,
            rate=from_rate,
        )

    to_rate = snapshot.rates.get(request.to_code)
    if to_rate is None:
        return None

    rub_amount = request.amount * from_rate.unit_rate
    return ConversionResult(request=request, result=rub_amount / to_rate.unit_rate, rate=from_rate)


def format_calculator_result(result: ConversionResult) -> str:
    request = result.request
    source = result.source
    rate = result.rate

    lines = [
        "💱 Расчёт валюты",
        "",
        f"{format_plain_amount(request.amount)} {request.from_code} по курсу {source}:",
        f"= {format_money(result.result, request.to_code)}",
        "",
        f"Курс: 1 {rate.code} = {format_rate(rate.unit_rate)} ₽",
        f"Дата курса: {rate.date.strftime('%d.%m.%Y')}",
        f"Источник: {source}",
        "",
        "Сформировано через @kurs_rub_bot",
    ]
    return "\n".join(lines)


def format_conversion(amount: Decimal, code: str, result_rub: Decimal) -> str:
    return f"{format_plain_amount(amount)} {code.upper()} = {format_number(result_rub)} RUB"
