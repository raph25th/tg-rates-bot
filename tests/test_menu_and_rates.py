from datetime import date, datetime
from decimal import Decimal

from handlers.start import (
    CAPABILITIES_BUTTON,
    CBR_CALC_BUTTON,
    CBR_RATES_BUTTON,
    INVESTING_CALC_BUTTON,
    INVESTING_RATES_BUTTON,
    main_menu_keyboard,
)
from handlers.rates import cbr_after_rates_keyboard, cbr_rates_menu_keyboard
from services.rates.base import Rate
from services.rates.formatter import format_cbr_rates
from services.rates.investing import get_investing_unavailable_message


def test_main_menu_contains_five_buttons() -> None:
    keyboard = main_menu_keyboard()
    texts = [button.text for row in keyboard.keyboard for button in row]

    assert texts == [
        CBR_RATES_BUTTON,
        INVESTING_RATES_BUTTON,
        CBR_CALC_BUTTON,
        INVESTING_CALC_BUTTON,
        CAPABILITIES_BUTTON,
    ]


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
        "USD:\n"
        "1 USD = 74,8806 ₽\n"
        "\n"
        "EUR:\n"
        "1 EUR = 85,3200 ₽"
    )


def test_investing_rates_unavailable_message() -> None:
    message = get_investing_unavailable_message()

    assert "📈 Курс Investing" in message
    assert "Live-курсы Investing скоро будут доступны." in message
    assert "Сейчас доступны расчёты по официальному курсу ЦБ РФ." in message
