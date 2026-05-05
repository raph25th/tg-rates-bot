from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def _normalize_currency_word(value: str) -> str:
    return value.strip(" \t\r\n.,;:!?()[]{}\"'«»").casefold().replace("ё", "е")


RUB_CODE = "RUB"
SUPPORTED_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "CNY", "GBP", "AED", "THB", "KRW", "JPY")
SKIP_WORDS = {"в", "to", "into", "на", "по", "цб"}
CURRENCY_ALIASES: dict[str, tuple[str, ...]] = {
    "USD": ("usd", "доллар", "доллара", "долларов", "доллары", "бакс", "бакса", "баксов", "юсд", "юэсд", "долл", "$"),
    "EUR": ("eur", "евро", "евра", "€"),
    "CNY": ("cny", "юань", "юаня", "юаней", "юани", "¥"),
    "GBP": ("gbp", "фунт", "фунта", "фунтов", "фунт стерлингов", "фунтов стерлингов", "£"),
    "AED": ("aed", "дирхам", "дирхама", "дирхамов", "дирхамы", "дирхам оаэ"),
    "THB": ("thb", "бат", "бата", "батов", "баты"),
    "KRW": ("krw", "вона", "воны", "вон", "корейская вона", "корейских вон"),
    "JPY": ("jpy", "иена", "йена", "иены", "йены", "иен", "йен", "¥"),
    RUB_CODE: ("rub", "ruble", "rubles", "rur", "руб", "руб.", "рубль", "рубля", "рублей", "₽"),
}
CURRENCY_ALIAS_TO_CODE: dict[str, str] = {}
for code, aliases in CURRENCY_ALIASES.items():
    for alias in aliases:
        normalized_alias = " ".join(
            part
            for part in (_normalize_currency_word(part) for part in alias.split())
            if part
        )
        if normalized_alias:
            CURRENCY_ALIAS_TO_CODE.setdefault(normalized_alias, code)
MAX_CURRENCY_ALIAS_WORDS = max(alias.count(" ") + 1 for alias in CURRENCY_ALIAS_TO_CODE)

_AMOUNT_RE = re.compile(
    r"^\s*(?P<amount>\d{1,3}(?:[ \t_.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?=\s|$|[$€£¥₽])",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(
    r"^(?:(?P<word>плюс|минус)|(?P<sign>[+-]))?\s*(?P<value>\d+(?:[.,]\d+)?)\s*%$",
    re.IGNORECASE,
)
_EXTRA_PAYMENT_RE = re.compile(
    r"^\+\s*(?P<amount>\d{1,3}(?:[ \t_.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(?P<label>пп|\$)?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConversionRequest:
    amount: Decimal
    from_currency: str
    to_currency: str
    percent_adjustment: Decimal | None
    extra_payment_amount: Decimal | None
    direction: str


def parse_conversion_request(text: str) -> ConversionRequest | None:
    amount_match = _AMOUNT_RE.match(text)
    if amount_match is None:
        return None

    amount = _parse_amount(amount_match.group("amount"))
    if amount is None or amount <= 0:
        return None

    raw_tokens = text[amount_match.end() :].strip().split()
    if not raw_tokens:
        return None

    percent: Decimal | None = None
    extra_payment_amount: Decimal | None = None
    tokens: list[str] = []
    index = 0
    while index < len(raw_tokens):
        token = raw_tokens[index]
        parsed_percent = _parse_percent_tokens(raw_tokens, index)
        if parsed_percent is not None:
            percent, consumed_tokens = parsed_percent
            index += consumed_tokens
            continue

        parsed_extra_payment = _parse_extra_payment_tokens(raw_tokens, index)
        if parsed_extra_payment is not None:
            extra_payment_amount, consumed_tokens = parsed_extra_payment
            index += consumed_tokens
            continue

        normalized = _normalize_currency_word(token)
        if normalized in SKIP_WORDS:
            index += 1
            continue

        tokens.append(token)
        index += 1

    if not tokens:
        return None

    currency_codes = _extract_currency_codes(tokens)
    if not currency_codes:
        return None

    if len(currency_codes) > 2:
        return None

    from_currency = currency_codes[0]
    to_currency = currency_codes[1] if len(currency_codes) == 2 else None

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
        extra_payment_amount=extra_payment_amount,
        direction=direction,
    )


def normalize_currency_token(value: str) -> str | None:
    token = " ".join(
        part
        for part in (_normalize_currency_word(part) for part in value.split())
        if part
    )
    if token in CURRENCY_ALIAS_TO_CODE:
        return CURRENCY_ALIAS_TO_CODE[token]
    if re.fullmatch(r"[a-z]{3}", token):
        return token.upper()
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


def _parse_amount(value: str) -> Decimal | None:
    compact = re.sub(r"[ \t_]", "", value)
    if "," in compact and "." in compact:
        decimal_separator = "," if compact.rfind(",") > compact.rfind(".") else "."
        thousand_separator = "." if decimal_separator == "," else ","
        normalized = compact.replace(thousand_separator, "").replace(decimal_separator, ".")
        return _parse_decimal(normalized)

    if "," in compact:
        return _parse_amount_with_single_separator(compact, ",")
    if "." in compact:
        return _parse_amount_with_single_separator(compact, ".")
    return _parse_decimal(compact)


def _parse_amount_with_single_separator(value: str, separator: str) -> Decimal | None:
    parts = value.split(separator)
    if len(parts) == 2:
        left, right = parts
        if len(right) == 3 and 1 <= len(left) <= 3:
            return _parse_decimal(left + right)
        return _parse_decimal(f"{left}.{right}")

    if len(parts) > 2 and 1 <= len(parts[0]) <= 3 and all(len(part) == 3 for part in parts[1:]):
        return _parse_decimal("".join(parts))
    return None


def _extract_currency_codes(tokens: list[str]) -> list[str] | None:
    codes: list[str] = []
    index = 0
    while index < len(tokens):
        max_words = min(MAX_CURRENCY_ALIAS_WORDS, len(tokens) - index)
        match: tuple[str, int] | None = None
        for size in range(max_words, 0, -1):
            code = normalize_currency_token(" ".join(tokens[index : index + size]))
            if code is not None:
                match = (code, size)
                break
        if match is None:
            return None
        code, size = match
        codes.append(code)
        index += size
    return codes


def _parse_percent_tokens(tokens: list[str], start_index: int) -> tuple[Decimal, int] | None:
    max_tokens = min(3, len(tokens) - start_index)
    for size in range(max_tokens, 0, -1):
        candidate = " ".join(tokens[start_index : start_index + size])
        parsed = _parse_percent(candidate)
        if parsed is not None:
            return parsed, size
    return None


def _parse_extra_payment_tokens(tokens: list[str], start_index: int) -> tuple[Decimal, int] | None:
    max_tokens = min(3, len(tokens) - start_index)
    for size in range(max_tokens, 0, -1):
        candidate = " ".join(tokens[start_index : start_index + size])
        parsed = _parse_extra_payment(candidate)
        if parsed is not None:
            return parsed, size
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
    if match.group("sign") == "-":
        return -abs(parsed)
    return parsed


def _parse_extra_payment(value: str) -> Decimal | None:
    match = _EXTRA_PAYMENT_RE.match(value)
    if match is None:
        return None

    parsed = _parse_amount(match.group("amount"))
    if parsed is None or parsed <= 0:
        return None
    return parsed
