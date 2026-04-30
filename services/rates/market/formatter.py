from __future__ import annotations

from collections.abc import Iterable

from core.money import format_rate
from services.rates.market.base import MARKET_RATE_ORDER, MarketRate


def format_market_rates(rates: dict[str, MarketRate], codes: Iterable[str] = MARKET_RATE_ORDER) -> str:
    first_rate = next((rates[code] for code in codes if code in rates), None)
    if first_rate is None:
        return "Курсы Investing временно недоступны. Проверьте настройки источника."

    lines = ["📈 Курсы Investing", "", f"Обновлено: {first_rate.fetched_at.strftime('%H:%M')} МСК"]
    for code in codes:
        rate = rates.get(code)
        if rate is None:
            continue
        lines.extend(["", f"{rate.pair}:", f"1 {rate.code} = {format_rate(rate.value)} ₽"])
    return "\n".join(lines)
