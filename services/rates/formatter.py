from __future__ import annotations

from collections.abc import Iterable

from core.money import format_rate
from services.rates.base import Rate


DEFAULT_RATE_ORDER: tuple[str, ...] = ("USD", "EUR", "CNY", "GBP", "AED", "THB", "KRW", "JPY")


def format_cbr_rates(rates: dict[str, Rate], codes: Iterable[str] = DEFAULT_RATE_ORDER) -> str:
    first_rate = next((rates[code] for code in codes if code in rates), None)
    if first_rate is None:
        return "Не удалось получить курсы ЦБ РФ по выбранным валютам."

    lines = [f"📊 Курсы ЦБ РФ на {first_rate.date.strftime('%d.%m.%Y')}"]
    for code in codes:
        rate = rates.get(code)
        if rate is None:
            continue
        lines.extend(
            [
                "",
                f"{rate.code}:",
                f"1 {rate.code} = {format_rate(rate.unit_rate)} ₽",
            ]
        )
    return "\n".join(lines)
