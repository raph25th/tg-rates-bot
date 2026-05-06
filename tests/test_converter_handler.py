from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from config import Settings
from core.models import CurrencyRate, RatesSnapshot
from handlers.converter import convert_currency as convert_currency_handler
from handlers.converter import (
    INVESTING_CALC_UNAVAILABLE_TEXT,
    MARKET_SOURCE,
    calculator_result_keyboard,
    get_capabilities_hint,
    get_new_calculation_hint,
    user_rate_source,
)
from services.rates.market import MarketRate


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
    assert "📉 Спред" in hint
    assert "Бот показывает разницу между курсом ЦБ РФ и рыночным курсом для USD, AED, CNY и EUR." in hint
    assert "🔔 Уведомления ЦБ" in hint
    assert "Бот может присылать курс ЦБ РФ после его обновления." in hint
    assert "100 usd" in hint
    assert "10 000 aed +2%" in hint
    assert "1 000 000 rub в usd" in hint
    assert "10 000 usd в руб -1,5%" in hint
    assert "50 200 CNY +2% +200ПП" in hint
    assert "Доп. платёж всегда считается в USD по тому же источнику курса и с той же ставкой." in hint
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
    assert "10 000 usd +2% +100ПП" in hint
    assert "50 200 CNY +2% +200ПП" in hint
    assert "Больше возможностей — в разделе:" in hint
    assert "❓ Что умеет бот" in hint


def test_calculator_result_keyboard_has_only_new_calc_and_main_menu() -> None:
    keyboard = calculator_result_keyboard()
    rows = [[(button.text, button.callback_data) for button in row] for row in keyboard.inline_keyboard]

    assert rows == [
        [
            ("🔁 Новый расчёт", "calc:new"),
            ("🏠 Главное меню", "main_menu"),
        ],
    ]
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "📋 Текст для клиента" not in texts


def test_investing_calculation_unavailable_message() -> None:
    assert "💱 Расчёт по рынку" in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "Рыночные курсы временно недоступны." in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "100 usd" in INVESTING_CALC_UNAVAILABLE_TEXT


class FakeCbrService:
    async def fetch_rates(self, target_date):
        rate_date = date(2026, 5, 5)
        return RatesSnapshot(
            date=rate_date,
            rates={
                "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
                "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("10.9500"), Decimal("10.9500"), rate_date),
            },
        )


class FakeMarketProvider:
    async def get_rate(self, code: str):
        return MarketRate(
            code=code,
            pair=f"{code}/RUB",
            value=Decimal("74.8850"),
            source="Yahoo Finance — рыночный ориентир",
            fetched_at=datetime(2026, 5, 5, 12, 0),
        )

    async def get_rates(self, codes: list[str]):
        values = {
            "USD": Decimal("74.8850"),
            "CNY": Decimal("10.9672"),
        }
        return {
            code: MarketRate(
                code=code,
                pair=f"{code}/RUB",
                value=values[code],
                source="Yahoo Finance — рыночный ориентир",
                fetched_at=datetime(2026, 5, 5, 12, 0),
            )
            for code in codes
        }


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=1001)
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


@pytest.mark.asyncio
async def test_successful_calculation_uses_client_format_and_two_buttons() -> None:
    message = FakeMessage("10000 usd +2% +100ПП")

    await convert_currency_handler(
        message,
        cbr_service=FakeCbrService(),
        app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
        market_rate_provider=None,
    )

    text, keyboard = message.answers[0]
    assert text == (
        "Расчёт стоимости:\n"
        "\n"
        "Сумма: 10 000 USD\n"
        "Актуальный курс: 1 USD = 75,0000 RUB\n"
        "Ставка: +2%\n"
        "Расчётный курс: 1 USD = 76,5000 RUB\n"
        "\n"
        "Основной платёж:\n"
        "10 000 USD = 765 000,00 RUB\n"
        "\n"
        "Доп. платёж:\n"
        "100 USD = 7 650,00 RUB\n"
        "\n"
        "Итого:\n"
        "765 000,00 RUB + 7 650,00 RUB = 772 650,00 RUB"
    )
    assert "Корректировка" not in text
    assert "ПП" not in text
    assert "Платёжка" not in text
    assert "₽" not in text
    assert keyboard is not None
    rows = [[button.text for button in row] for row in keyboard.inline_keyboard]
    assert rows == [["🔁 Новый расчёт", "🏠 Главное меню"]]


@pytest.mark.asyncio
async def test_market_calculation_uses_same_client_format_with_extra_payment() -> None:
    user_rate_source[1001] = MARKET_SOURCE
    message = FakeMessage("50200 CNY +2% +200ПП")

    try:
        await convert_currency_handler(
            message,
            cbr_service=FakeCbrService(),
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=FakeMarketProvider(),
        )

        text, keyboard = message.answers[0]
        assert text == (
            "Расчёт стоимости:\n"
            "\n"
            "Сумма: 50 200 CNY\n"
            "Актуальный курс: 1 CNY = 10,9672 RUB\n"
            "Ставка: +2%\n"
            "Расчётный курс: 1 CNY = 11,1865 RUB\n"
            "\n"
            "Основной платёж:\n"
            "50 200 CNY = 561 564,51 RUB\n"
            "\n"
            "Доп. платёж:\n"
            "200 USD × 76,3827 RUB = 15 276,54 RUB\n"
            "\n"
            "Итого:\n"
            "561 564,51 RUB + 15 276,54 RUB = 576 841,05 RUB"
        )
        assert "Источник:" not in text
        assert "Yahoo Finance" not in text
        assert "💱 Расчёт по рыночному курсу" not in text
        assert "💱 Расчёт по курсу ЦБ РФ" not in text
        assert "📋 Текст для клиента" not in [button.text for row in keyboard.inline_keyboard for button in row]
    finally:
        user_rate_source.pop(1001, None)
