from datetime import date, datetime
from decimal import Decimal

import pytest

from config import Settings
from core.models import CurrencyRate, RatesSnapshot
from handlers.start import (
    AGENT_CBR_CALC_BUTTON,
    AGENT_MARKET_CALC_BUTTON,
    CAPABILITIES_BUTTON,
    CBR_CALC_BUTTON,
    CBR_NOTIFICATIONS_BUTTON,
    CBR_RATES_BUTTON,
    INVESTING_CALC_BUTTON,
    INVESTING_RATES_BUTTON,
    SPREAD_BUTTON,
    main_menu_keyboard,
)
from handlers.rates import (
    _answer_latest_cbr_rates,
    _fetch_rates_for_requested_date,
    cbr_after_rates_keyboard,
    cbr_rates_menu_keyboard,
    show_cbr_rates_button,
)
from services.rates.base import Rate
from services.rates.formatter import format_cbr_rates
from services.rates.investing import get_investing_unavailable_message


def test_main_menu_contains_agent_buttons() -> None:
    keyboard = main_menu_keyboard()
    texts = [button.text for row in keyboard.keyboard for button in row]

    assert texts == [
        CBR_RATES_BUTTON,
        INVESTING_RATES_BUTTON,
        CBR_CALC_BUTTON,
        INVESTING_CALC_BUTTON,
        AGENT_CBR_CALC_BUTTON,
        AGENT_MARKET_CALC_BUTTON,
        SPREAD_BUTTON,
        CBR_NOTIFICATIONS_BUTTON,
        CAPABILITIES_BUTTON,
    ]
    assert INVESTING_RATES_BUTTON == "📈 Рыночный курс"
    assert INVESTING_CALC_BUTTON == "💱 Расчёт по рынку"
    assert AGENT_CBR_CALC_BUTTON == "🤝 Агентский расчёт по ЦБ РФ"
    assert AGENT_MARKET_CALC_BUTTON == "🤝 Агентский расчёт по рынку"
    assert SPREAD_BUTTON == "📉 Спред"
    assert CBR_NOTIFICATIONS_BUTTON == "🔔 Уведомления ЦБ"
    assert all("Investing" not in text for text in texts)


def test_cbr_rates_menu_contains_date_actions() -> None:
    keyboard = cbr_rates_menu_keyboard()
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert texts == ["📅 Сегодня", "🗓 Выбрать дату", "🏠 Главное меню"]
    assert callbacks == ["cbr:today", "cbr:choose_date", "main_menu"]


def test_cbr_after_rates_keyboard_contains_repeat_and_menu() -> None:
    keyboard = cbr_after_rates_keyboard()
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

    assert texts == ["🗓 Выбрать другую дату", "🏠 Главное меню"]
    assert callbacks == ["cbr:choose_date", "main_menu"]


def test_format_cbr_rates_button_output() -> None:
    rate_date = date(2026, 4, 30)
    fetched_at = datetime(2026, 4, 30, 14, 35)
    rates = {
        "USD": Rate("USD", "Доллар США", 1, Decimal("74.8806"), Decimal("74.8806"), rate_date, "CBR", fetched_at),
        "EUR": Rate("EUR", "Евро", 1, Decimal("85.3200"), Decimal("85.3200"), rate_date, "CBR", fetched_at),
    }

    assert format_cbr_rates(rates, ("USD", "EUR")) == (
        "📊 Курсы ЦБ РФ на 30.04.2026\n"
        "\n"
        "<code>USD/RUB — Доллар США\n"
        "1 USD = 74,8806</code>\n"
        "\n"
        "<code>EUR/RUB — Евро\n"
        "1 EUR = 85,3200</code>"
    )


def test_format_cbr_rates_uses_fixed_display_names() -> None:
    rate_date = date(2026, 5, 5)
    fetched_at = datetime(2026, 5, 5, 14, 35)
    rates = {
        "CNY": Rate("CNY", "Юань", 1, Decimal("11.0343"), Decimal("11.0343"), rate_date, "CBR", fetched_at),
        "THB": Rate("THB", "Таиландский бат", 1, Decimal("2.3021"), Decimal("2.3021"), rate_date, "CBR", fetched_at),
        "KRW": Rate("KRW", "Вона Республики Корея", 1, Decimal("0.0508"), Decimal("0.0508"), rate_date, "CBR", fetched_at),
    }

    message = format_cbr_rates(rates, ("CNY", "THB", "KRW"))

    assert "<code>CNY/RUB — Китайский юань\n1 CNY = 11,0343</code>" in message
    assert "<code>THB/RUB — Тайский бат\n1 THB = 2,3021</code>" in message
    assert "<code>KRW/RUB — Южнокорейская вона\n1 KRW = 0,0508</code>" in message


def test_format_cbr_rates_escapes_html_in_rate_blocks() -> None:
    rate_date = date(2026, 5, 5)
    fetched_at = datetime(2026, 5, 5, 14, 35)
    rates = {
        "XXX": Rate("XXX", "A&B <test>", 1, Decimal("1.2345"), Decimal("1.2345"), rate_date, "CBR", fetched_at),
    }

    assert "<code>XXX/RUB — A&amp;B &lt;test&gt;\n1 XXX = 1,2345</code>" in format_cbr_rates(rates, ("XXX",))


def test_format_cbr_rates_has_no_ruble_symbol_after_rate_values() -> None:
    rate_date = date(2026, 5, 5)
    fetched_at = datetime(2026, 5, 5, 14, 35)
    rates = {
        "USD": Rate("USD", "Доллар США", 1, Decimal("75.4388"), Decimal("75.4388"), rate_date, "CBR", fetched_at),
    }

    message = format_cbr_rates(rates, ("USD",))

    assert "1 USD = 75,4388</code>" in message
    assert "1 USD = 75,4388 ₽" not in message


def test_investing_rates_unavailable_message() -> None:
    message = get_investing_unavailable_message()

    assert "📈 Рыночный курс" in message
    assert "Рыночные курсы временно недоступны." in message
    assert "Попробуйте позже или используйте курс ЦБ РФ." in message


class FakeCbrService:
    def __init__(self) -> None:
        self.fetch_latest_calls = 0
        self.fetch_rate_dates: list[date] = []

    def _snapshot(self, rate_date: date) -> RatesSnapshot:
        return RatesSnapshot(
            date=rate_date,
            rates={
                "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
            },
        )

    async def get_latest_cbr_rates(self) -> RatesSnapshot:
        self.fetch_latest_calls += 1
        return self._snapshot(date(2026, 5, 15))

    async def fetch_latest_rates(self) -> RatesSnapshot:
        return await self.get_latest_cbr_rates()

    async def fetch_rates(self, target_date: date) -> RatesSnapshot:
        self.fetch_rate_dates.append(target_date)
        return self._snapshot(target_date)


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, reply_markup=None, parse_mode=None) -> None:
        self.answers.append({"text": text, "reply_markup": reply_markup, "parse_mode": parse_mode})


@pytest.mark.asyncio
async def test_cbr_rates_screen_uses_latest_cbr_date_from_response() -> None:
    cbr_service = FakeCbrService()
    message = FakeMessage()

    await _answer_latest_cbr_rates(
        message,
        cbr_service,
        Settings(bot_token="123:test", timezone="Europe/Moscow"),
    )

    assert cbr_service.fetch_latest_calls == 1
    assert cbr_service.fetch_rate_dates == []
    assert "📊 Курсы ЦБ РФ на 15.05.2026" in message.answers[0]["text"]


@pytest.mark.asyncio
async def test_cbr_rates_button_uses_latest_cbr_date_from_response() -> None:
    cbr_service = FakeCbrService()
    message = FakeMessage()

    await show_cbr_rates_button(
        message,
        cbr_service,
        Settings(bot_token="123:test", timezone="Europe/Moscow"),
    )

    assert cbr_service.fetch_latest_calls == 1
    assert cbr_service.fetch_rate_dates == []
    assert "📊 Курсы ЦБ РФ на 15.05.2026" in message.answers[0]["text"]


@pytest.mark.asyncio
async def test_cbr_today_action_uses_latest_cbr_date_not_calendar_today() -> None:
    cbr_service = FakeCbrService()
    message = FakeMessage()

    await _answer_latest_cbr_rates(
        message,
        cbr_service,
        Settings(bot_token="123:test", timezone="Europe/Moscow"),
    )

    assert cbr_service.fetch_latest_calls == 1
    assert cbr_service.fetch_rate_dates == []
    assert "📊 Курсы ЦБ РФ на 15.05.2026" in message.answers[0]["text"]


@pytest.mark.asyncio
async def test_manual_cbr_date_uses_requested_date() -> None:
    cbr_service = FakeCbrService()

    text, warning = await _fetch_rates_for_requested_date(
        cbr_service,
        date(2026, 4, 23),
        datetime(2026, 5, 14, 17, 0),
    )

    assert cbr_service.fetch_latest_calls == 0
    assert cbr_service.fetch_rate_dates == [date(2026, 4, 23)]
    assert warning is None
    assert "📊 Курсы ЦБ РФ на 23.04.2026" in text
