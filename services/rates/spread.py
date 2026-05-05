from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable

from core.money import format_number, format_rate
from services.rates.base import Rate
from services.rates.display import currency_display_name
from services.rates.market.base import MarketRate


SPREAD_RATE_ORDER: tuple[str, ...] = ("USD", "EUR", "CNY")


@dataclass(frozen=True)
class SpreadRate:
    code: str
    cbr_rate: Decimal
    market_rate: Decimal
    difference: Decimal
    percent: Decimal
    updated_at: datetime


def calculate_spread(
    cbr_rates: dict[str, Rate],
    market_rates: dict[str, MarketRate],
    codes: Iterable[str] = SPREAD_RATE_ORDER,
) -> list[SpreadRate]:
    spreads: list[SpreadRate] = []
    for code in codes:
        cbr_rate = cbr_rates.get(code)
        market_rate = market_rates.get(code)
        if cbr_rate is None or market_rate is None or cbr_rate.unit_rate == 0:
            continue

        difference = market_rate.value - cbr_rate.unit_rate
        percent = difference / cbr_rate.unit_rate * Decimal("100")
        spreads.append(
            SpreadRate(
                code=code,
                cbr_rate=cbr_rate.unit_rate,
                market_rate=market_rate.value,
                difference=difference,
                percent=percent,
                updated_at=market_rate.fetched_at,
            )
        )
    return spreads


def _format_signed_rate(value: Decimal) -> str:
    text = format_rate(value)
    return f"+{text}" if value > 0 else text


def _format_signed_percent(value: Decimal) -> str:
    text = format_number(value, places=2, trim_zero_fraction=False)
    return f"+{text}" if value > 0 else text


def _format_spread_block(spread: SpreadRate) -> str:
    return "\n".join(
        [
        f"{spread.code}/RUB — {currency_display_name(spread.code)}",
        f"ЦБ РФ: {format_rate(spread.cbr_rate)}",
        f"Рынок: {format_rate(spread.market_rate)}",
        f"Разница: {_format_signed_rate(spread.difference)}",
        f"Спред: {_format_signed_percent(spread.percent)}%",
        ]
    )


def format_spread_message(spreads: list[SpreadRate]) -> str:
    if not spreads:
        return "Не удалось сравнить курсы ЦБ РФ и рынка. Попробуйте позже."

    lines = ["📉 Спред ЦБ РФ / рынок"]
    for spread in spreads:
        lines.extend(["", _format_spread_block(spread)])

    lines.extend(["", "Обновлено:", f"{spreads[0].updated_at.strftime('%H:%M')} МСК"])
    return "\n".join(lines)
