from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from core.models import CurrencyRate, RatesSnapshot
from handlers.converter import (
    INVESTING_CALC_UNAVAILABLE_TEXT,
    calculator_result_keyboard,
    get_capabilities_hint,
    get_client_text_for_user,
    get_new_calculation_hint,
    last_calculations,
    show_client_text,
)
from services.converter import convert_currency, parse_convert_request


def test_capabilities_hint_covers_supported_examples() -> None:
    hint = get_capabilities_hint()

    assert "❓ Что умеет бот" in hint
    assert "Бот помогает быстро считать валюту по официальному курсу ЦБ РФ и рыночному ориентиру." in hint
    assert "📊 Курс ЦБ РФ" in hint
    assert "Официальный курс Банка России. Обновляется один раз в день." in hint
    assert "📈 Рыночный курс" in hint
    assert "Ориентировочный курс в моменте по данным Yahoo Finance." in hint
    assert "🧮 Расчёт по ЦБ РФ" in hint
    assert "💱 Расчёт по рынку" in hint
    assert "🔔 Уведомления ЦБ" in hint
    assert "Бот может присылать курс ЦБ РФ после его обновления." in hint
    assert "100 usd" in hint
    assert "10 000 aed +2%" in hint
    assert "1 000 000 rub в usd" in hint
    assert "10 000 usd в руб -1,5%" in hint
    assert "Можно писать как код валюты, так и словами:" in hint
    assert "10 000 долларов" in hint
    assert "1 000 000 рублей в евро" in hint
    assert "USD, EUR, CNY, GBP, AED, THB, KRW, JPY" in hint


def test_new_calculation_hint_is_short() -> None:
    hint = get_new_calculation_hint()

    assert "💱 Новый расчёт" in hint
    assert "100 usd" in hint
    assert "10 000 usd +2%" in hint
    assert "1 000 000 rub в usd" in hint
    assert "Больше возможностей — в разделе:" in hint
    assert "❓ Что умеет бот" in hint


def make_result(text: str = "100 usd +2%"):
    rate_date = date(2026, 4, 30)
    snapshot = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("74.8806"), Decimal("74.8806"), rate_date),
        },
    )
    request = parse_convert_request(text)
    assert request is not None
    result = convert_currency(request, snapshot, source="ЦБ РФ — официальный курс")
    assert result is not None
    return result


def test_calculator_result_keyboard_has_client_text_new_calc_and_main_menu() -> None:
    keyboard = calculator_result_keyboard()
    rows = [[(button.text, button.callback_data) for button in row] for row in keyboard.inline_keyboard]

    assert rows == [
        [("📋 Текст для клиента", "calc:client_text")],
        [
            ("🔁 Новый расчёт", "calc:new"),
            ("🏠 Главное меню", "main_menu"),
        ],
    ]


def test_client_text_for_user_uses_last_calculation_with_rate_label() -> None:
    last_calculations.clear()
    last_calculations[1001] = make_result("100 usd +2%")

    text = get_client_text_for_user(1001)

    assert "Ставка: +2%" in text
    assert "Корректировка" not in text
    assert "Источник" not in text
    assert "Yahoo Finance" not in text


def test_client_text_for_user_without_percent_omits_rate_label() -> None:
    last_calculations.clear()
    last_calculations[1001] = make_result("100 usd")

    text = get_client_text_for_user(1001)

    assert "Ставка" not in text
    assert "Расчётный курс" not in text
    assert "Корректировка" not in text


def test_client_text_for_user_without_last_calculation_shows_hint() -> None:
    last_calculations.clear()

    assert get_client_text_for_user(1001) == (
        "Сначала выполните расчёт, например:\n"
        "\n"
        "100 usd\n"
        "10 000 usd +2%\n"
        "1 000 000 rub в usd"
    )


class FakeCallbackMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


class FakeCallback:
    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeCallbackMessage()
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


@pytest.mark.asyncio
async def test_client_text_callback_sends_client_text_without_keyboard() -> None:
    last_calculations.clear()
    last_calculations[1001] = make_result("100 usd +2%")
    callback = FakeCallback(1001)

    await show_client_text(callback)

    assert callback.answered is True
    assert len(callback.message.answers) == 1
    text, reply_markup = callback.message.answers[0]
    assert "Ставка: +2%" in text
    assert "Корректировка" not in text
    assert "Источник" not in text
    assert reply_markup is None


@pytest.mark.asyncio
async def test_client_text_callback_without_last_calculation_shows_hint() -> None:
    last_calculations.clear()
    callback = FakeCallback(1001)

    await show_client_text(callback)

    assert callback.message.answers[0][0].startswith("Сначала выполните расчёт")


def test_investing_calculation_unavailable_message() -> None:
    assert "💱 Расчёт по рынку" in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "Рыночные курсы временно недоступны." in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "100 usd" in INVESTING_CALC_UNAVAILABLE_TEXT
