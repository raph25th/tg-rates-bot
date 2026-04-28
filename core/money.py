from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CURRENCY_SYMBOLS: dict[str, str] = {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "CNY": "¥",
    "GBP": "£",
    "AED": "AED",
    "JPY": "¥",
    "KRW": "₩",
    "THB": "฿",
}


def format_number(value: Decimal, places: int = 2, trim_zero_fraction: bool = True) -> str:
    quant = Decimal("1").scaleb(-places)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    text = f"{rounded:.{places}f}"
    if places == 0:
        whole = text
        fraction = ""
    else:
        whole, fraction = text.split(".")

    sign = ""
    if whole.startswith("-"):
        sign = "-"
        whole = whole[1:]

    parts: list[str] = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    grouped = sign + " ".join(reversed(parts or ["0"]))

    if places == 0 or (trim_zero_fraction and set(fraction) == {"0"}):
        return grouped
    return f"{grouped},{fraction}"


def format_money(value: Decimal, code: str, places: int = 2) -> str:
    symbol = CURRENCY_SYMBOLS.get(code.upper(), code.upper())
    return f"{format_number(value, places=places)} {symbol}"


def format_rate(value: Decimal) -> str:
    quant = Decimal("0.0001")
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    return f"{rounded:.4f}".replace(".", ",")


def format_plain_amount(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format_number(normalized, places=0)
    return format_number(value, places=2)
