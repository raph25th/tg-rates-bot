from datetime import date, datetime
from decimal import Decimal

from handlers.start import (
    CAPABILITIES_BUTTON,
    CBR_CALC_BUTTON,
    CBR_NOTIFICATIONS_BUTTON,
    CBR_RATES_BUTTON,
    INVESTING_CALC_BUTTON,
    INVESTING_RATES_BUTTON,
    SPREAD_BUTTON,
    main_menu_keyboard,
)
from handlers.rates import cbr_after_rates_keyboard, cbr_rates_menu_keyboard
from services.rates.base import Rate
from services.rates.formatter import format_cbr_rates
from services.rates.investing import get_investing_unavailable_message


def test_main_menu_contains_seven_buttons() -> None:
    keyboard = main_menu_keyboard()
    texts = [button.text for row in keyboard.keyboard for button in row]

    assert texts == [
        CBR_RATES_BUTTON,
        INVESTING_RATES_BUTTON,
        CBR_CALC_BUTTON,
        INVESTING_CALC_BUTTON,
        SPREAD_BUTTON,
        CBR_NOTIFICATIONS_BUTTON,
        CAPABILITIES_BUTTON,
    ]
    assert INVESTING_RATES_BUTTON == "📈 Рыночный курс"
    assert INVESTING_CALC_BUTTON == "💱 Расчёт по рынку"
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
