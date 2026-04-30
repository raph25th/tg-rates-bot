from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

RUB_CODE = "RUB"
SUPPORTED_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "CNY", "GBP", "AED", "THB", "KRW", "JPY")
RUB_ALIASES = {"rub", "ruble", "rubles", "rur", "руб", "руб.", "рубль", "рубля", "рублей", "₽"}
SKIP_WORDS = {"в", "to", "into", "на", "по", "цб"}

_AMOUNT_RE = re.compile(
    r"^\s*(?P<amount>\d+(?:[\s_]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(
    r"^(?:(?P<word>плюс|минус)\s+)?(?P<value>[+-]?\d+(?:[.,]\d+)?)%$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConversionRequest:
    amount: Decimal
    from_currency: str
    to_currency: str
    percent_adjustment: Decimal | None
    direction: str


def parse_conversion_request(text: str) -> ConversionRequest | None:
    amount_match = _AMOUNT_RE.match(text)
    if amount_match is None:
        return None

    amount = _parse_decimal(amount_match.group("amount").replace(" ", "").replace("_", ""))
    if amount is None or amount <= 0:
        return None

    raw_tokens = text[amount_match.end() :].strip().split()
    if not raw_tokens:
        return None

    percent: Decimal | None = None
    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        joined_percent = None
        if token.lower() in {"плюс", "минус"} and index + 1 < len(raw_tokens):
            joined_percent = f"{token} {raw_tokens[index + 1]}"

        if joined_percent is not None and _PERCENT_RE.match(joined_percent):
            percent = _parse_percent(joined_percent)
            index += 2
            continue

        if _PERCENT_RE.match(token):
            percent = _parse_percent(token)
            index += 1
            continue

        normalized = token.strip().lower()
        if normalized in SKIP_WORDS:
            index += 1
            continue

        tokens.append(token)
        index += 1

    if not tokens:
        return None

    from_currency = normalize_currency_token(tokens[0])
    if from_currency is None:
        return None

    if len(tokens) > 2:
        return None

    to_currency = normalize_currency_token(tokens[1]) if len(tokens) == 2 else None
    if len(tokens) == 2 and to_currency is None:
        return None

    if from_currency == RUB_CODE:
        if to_currency is None or to_currency == RUB_CODE:
            return None
        direction = "rub_to_currency"
    else:
        if to_currency is None:
            to_currency = RUB_CODE
        if to_currency != RUB_CODE:
            return None
        direction = "currency_to_rub"

    return ConversionRequest(
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency,
        percent_adjustment=percent,
        direction=direction,
    )


def normalize_currency_token(value: str) -> str | None:
    token = value.strip().lower()
    if token in RUB_ALIASES:
        return RUB_CODE
    if re.fullmatch(r"[a-zA-Z]{3}", value):
        return value.upper()
    return None


def looks_like_convert_attempt(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if any(char.isdigit() for char in text):
        return True
    return re.search(r"\b[a-zA-Z]{3}\b", text) is not None


def is_supported_currency(code: str) -> bool:
    return code.upper() in SUPPORTED_CURRENCIES


def is_supported_conversion_request(request: ConversionRequest) -> bool:
    if request.direction == "rub_to_currency":
        return is_supported_currency(request.to_currency)
    return is_supported_currency(request.from_currency)


def _parse_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        return None


def _parse_percent(value: str) -> Decimal | None:
    match = _PERCENT_RE.match(value)
    if match is None:
        return None

    parsed = _parse_decimal(match.group("value").lstrip("+"))
    if parsed is None:
        return None

    word = (match.group("word") or "").lower()
    if word == "минус":
        return -abs(parsed)
    if word == "плюс":
        return abs(parsed)
    return parsed
