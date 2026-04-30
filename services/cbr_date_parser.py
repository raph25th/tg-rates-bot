from __future__ import annotations

import re
from datetime import date


MONTHS: dict[str, int] = {
    "январь": 1,
    "января": 1,
    "янв": 1,
    "jan": 1,
    "февраль": 2,
    "февраля": 2,
    "фев": 2,
    "feb": 2,
    "март": 3,
    "марта": 3,
    "мар": 3,
    "mar": 3,
    "апрель": 4,
    "апреля": 4,
    "апр": 4,
    "apr": 4,
    "май": 5,
    "мая": 5,
    "may": 5,
    "июнь": 6,
    "июня": 6,
    "июн": 6,
    "jun": 6,
    "июль": 7,
    "июля": 7,
    "июл": 7,
    "jul": 7,
    "август": 8,
    "августа": 8,
    "авг": 8,
    "aug": 8,
    "сентябрь": 9,
    "сентября": 9,
    "сен": 9,
    "сент": 9,
    "sep": 9,
    "октябрь": 10,
    "октября": 10,
    "окт": 10,
    "oct": 10,
    "ноябрь": 11,
    "ноября": 11,
    "ноя": 11,
    "nov": 11,
    "декабрь": 12,
    "декабря": 12,
    "дек": 12,
    "dec": 12,
}

NUMERIC_DATE_RE = re.compile(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*$")
MONTH_NAME_RE = re.compile(r"^\s*(\d{1,2})\s+([а-яёa-z.]+)(?:\s+(\d{4}))?\s*$", re.IGNORECASE)


def parse_cbr_date(value: str, *, today: date | None = None) -> date | None:
    current_date = today or date.today()
    text = value.strip().lower().replace("ё", "е")

    numeric_match = NUMERIC_DATE_RE.match(text)
    if numeric_match:
        day, month, year = (int(part) for part in numeric_match.groups())
        return _safe_date(year, month, day)

    month_match = MONTH_NAME_RE.match(text)
    if month_match:
        day_text, month_text, year_text = month_match.groups()
        month = MONTHS.get(month_text.rstrip("."))
        if month is None:
            return None
        year = int(year_text) if year_text else current_date.year
        return _safe_date(year, month, int(day_text))

    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None
