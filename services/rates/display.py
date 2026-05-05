from __future__ import annotations

from html import escape


CURRENCY_DISPLAY_NAMES: dict[str, str] = {
    "USD": "Доллар США",
    "EUR": "Евро",
    "CNY": "Китайский юань",
    "GBP": "Фунт стерлингов",
    "AED": "Дирхам ОАЭ",
    "THB": "Тайский бат",
    "KRW": "Южнокорейская вона",
    "JPY": "Японская иена",
}


def currency_display_name(code: str, fallback: str | None = None) -> str:
    return CURRENCY_DISPLAY_NAMES.get(code.upper(), fallback or code.upper())


def format_html_rate_block(title: str, rate_line: str) -> str:
    return f"<code>{escape(title)}\n{escape(rate_line)}</code>"
