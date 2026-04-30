from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence

from services.cbr import RatesSnapshot

DEFAULT_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "CNY", "GBP", "AED", "THB", "KRW", "JPY")
SUPPORTED_CURRENCIES: tuple[str, ...] = (
    "USD",
    "EUR",
    "CNY",
    "GBP",
    "AED",
    "THB",
    "KRW",
    "JPY",
)


def normalize_currency_codes(codes: Iterable[str]) -> list[str]:
    unique = {code.strip().upper() for code in codes if code and code.strip()}
    ordered = [code for code in SUPPORTED_CURRENCIES if code in unique]
    ordered.extend(sorted(unique.difference(SUPPORTED_CURRENCIES)))
    return ordered


def format_decimal(value: Decimal, places: int) -> str:
    quant = Decimal("1").scaleb(-places)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:.{places}f}".replace(".", ",")


def format_delta(value: Decimal) -> str:
    quant = Decimal("0.01")
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    sign = "+" if rounded > 0 else ""
    if rounded == 0:
        rounded = abs(rounded)
    return f"{sign}{format_decimal(rounded, 2)}"


def format_rates(snapshot: RatesSnapshot, codes: Sequence[str]) -> str:
    lines = [f"Курсы ЦБ РФ на {snapshot.date.strftime('%d.%m.%Y')}:"]

    for code in normalize_currency_codes(codes):
        rate = snapshot.rates.get(code)
        if rate is None:
            continue

        delta = snapshot.deltas.get(code)
        delta_text = f" ({format_delta(delta)})" if delta is not None else ""
        lines.extend(
            [
                "",
                f"Курс {rate.code} к RUB:",
                f"1 {rate.name} = {format_decimal(rate.unit_rate, 4)}{delta_text} руб.",
            ]
        )

    if len(lines) == 1:
        lines.extend(["", "Нет данных по выбранным валютам."])

    return "\n".join(lines)
