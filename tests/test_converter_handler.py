from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from config import Settings
from core.models import CurrencyRate, RatesSnapshot
from handlers.converter import convert_currency as convert_currency_handler
from handlers.converter import (
    AGENT_CBR_SOURCE,
    AGENT_CUSTOM_SOURCE,
    AGENT_MARKET_SOURCE,
    AGENT_RATE_TOO_LOW_TEXT,
    AGENT_REVERSE_UNSUPPORTED_TEXT,
    CBR_SOURCE,
    CUSTOM_SOURCE,
    INVESTING_CALC_UNAVAILABLE_TEXT,
    MAX_INVOICE_SOURCE,
    MARKET_SOURCE,
    agent_calculation_keyboard,
    calculator_result_keyboard,
    choose_agent_custom_calculation,
    choose_agent_cbr_calculation,
    choose_agent_market_calculation,
    choose_cbr_calculation,
    choose_max_invoice_calculation,
    choose_custom_calculation,
    format_agent_assignment_text,
    get_capabilities_hint,
    get_agent_assignment_text_for_user,
    get_new_calculation_hint,
    last_agent_calculations,
    show_agent_assignment_text,
    user_rate_source,
)
from services.converter import convert_agent_calculation, parse_convert_request
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
    assert "Бот присылает курс ЦБ РФ после обновления и показывает, насколько курс вырос или снизился относительно предыдущего опубликованного курса." in hint
    assert "100 usd" in hint
    assert "10 000 aed +2%" in hint
    assert "1 000 000 rub в usd" in hint
    assert "10 000 usd в руб -1,5%" in hint
    assert "50 200 CNY +2% +200ПП" in hint
    assert "Доп. платёж всегда считается в USD по тому же источнику курса и с той же ставкой." in hint
    assert "Агентский расчёт:" in hint
    assert "10 000 USD +2,5%" in hint
    assert "50 200 CNY +2,5% +200ПП" in hint
    assert "В агентском расчёте ставка клиента делится на основную ставку и агентское вознаграждение 0,1%." in hint
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
    assert "10 000 USD +2,5%" in hint
    assert "50 200 CNY +2,5% +200ПП" in hint
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
    assert "📄 Версия для поручения" not in texts


def test_agent_calculation_keyboard_has_assignment_new_calc_and_main_menu() -> None:
    keyboard = agent_calculation_keyboard()
    rows = [[(button.text, button.callback_data) for button in row] for row in keyboard.inline_keyboard]

    assert rows == [
        [("📄 Версия для поручения", "agent:assignment_text")],
        [
            ("🔁 Новый расчёт", "calc:new"),
            ("🏠 Главное меню", "main_menu"),
        ],
    ]


def test_investing_calculation_unavailable_message() -> None:
    assert "💱 Расчёт по рынку" in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "Рыночные курсы временно недоступны." in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "100 usd" in INVESTING_CALC_UNAVAILABLE_TEXT


@pytest.mark.asyncio
async def test_choose_cbr_calculation_resets_previous_agent_source() -> None:
    message = FakeMessage()
    user_rate_source[1001] = AGENT_CBR_SOURCE

    try:
        await choose_cbr_calculation(message)

        assert user_rate_source[1001] == CBR_SOURCE
        assert "Расчёт по ЦБ РФ" in message.answers[0][0]
    finally:
        user_rate_source.pop(1001, None)


class FakeCbrService:
    def __init__(self) -> None:
        self.fetch_latest_calls = 0
        self.fetch_rate_dates: list[date] = []

    def _snapshot(self) -> RatesSnapshot:
        rate_date = date(2026, 5, 5)
        return RatesSnapshot(
            date=rate_date,
            rates={
                "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
                "EUR": CurrencyRate("EUR", "Евро", 1, Decimal("88.0000"), Decimal("88.0000"), rate_date),
                "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("10.9500"), Decimal("10.9500"), rate_date),
                "AED": CurrencyRate("AED", "Дирхам ОАЭ", 1, Decimal("21.3250"), Decimal("21.3250"), rate_date),
            },
        )

    async def fetch_rates(self, target_date):
        self.fetch_rate_dates.append(target_date)
        return self._snapshot()

    async def get_latest_cbr_rates(self):
        self.fetch_latest_calls += 1
        return self._snapshot()

    async def fetch_latest_rates(self):
        return await self.get_latest_cbr_rates()


class FakeMarketProvider:
    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    async def get_rate(self, code: str):
        return MarketRate(
            code=code,
            pair=f"{code}/RUB",
            value=Decimal("74.8850"),
            source="Yahoo Finance — рыночный ориентир",
            fetched_at=datetime(2026, 5, 5, 12, 0),
        )

    async def get_rates(self, codes: list[str]):
        self.requests.append(list(codes))
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
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.from_user = SimpleNamespace(id=1001)
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


class FakeCallbackMessage:
    def __init__(self) -> None:
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


class FakeCallback:
    def __init__(self, user_id: int = 1001) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeCallbackMessage()
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


@pytest.mark.asyncio
async def test_successful_calculation_uses_client_format_and_two_buttons() -> None:
    message = FakeMessage("10000 usd +2% +100ПП")
    cbr_service = FakeCbrService()

    await convert_currency_handler(
        message,
        cbr_service=cbr_service,
        app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
        market_rate_provider=None,
    )

    assert cbr_service.fetch_latest_calls == 1
    assert cbr_service.fetch_rate_dates == []
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


@pytest.mark.asyncio
async def test_agent_cbr_button_sets_mode_and_shows_hint() -> None:
    user_rate_source.pop(1001, None)
    message = FakeMessage()

    await choose_agent_cbr_calculation(message)

    assert user_rate_source[1001] == AGENT_CBR_SOURCE
    assert message.answers[0][0].startswith("🤝 Агентский расчёт по ЦБ РФ")
    assert "10 000 USD +2,5% +100ПП" in message.answers[0][0]
    user_rate_source.pop(1001, None)


@pytest.mark.asyncio
async def test_agent_market_button_sets_mode_and_shows_hint() -> None:
    user_rate_source.pop(1001, None)
    message = FakeMessage()

    await choose_agent_market_calculation(message, FakeMarketProvider())

    assert user_rate_source[1001] == AGENT_MARKET_SOURCE
    assert message.answers[0][0].startswith("🤝 Агентский расчёт по рынку")
    assert "50 200 CNY +2,5% +200ПП" in message.answers[0][0]
    user_rate_source.pop(1001, None)


@pytest.mark.asyncio
async def test_custom_button_sets_mode_and_shows_hint() -> None:
    user_rate_source.pop(1001, None)
    message = FakeMessage()

    await choose_custom_calculation(message)

    assert user_rate_source[1001] == CUSTOM_SOURCE
    assert message.answers[0][0].startswith("🧮 Расчёт по своему курсу")
    assert "76,50 10 000 USD" in message.answers[0][0]
    user_rate_source.pop(1001, None)


@pytest.mark.asyncio
async def test_agent_custom_button_sets_mode_and_shows_hint() -> None:
    user_rate_source.pop(1001, None)
    message = FakeMessage()

    await choose_agent_custom_calculation(message)

    assert user_rate_source[1001] == AGENT_CUSTOM_SOURCE
    assert message.answers[0][0].startswith("🤝 Агентский расчёт по своему курсу")
    assert "76.50 10 000 USD +2,5% +100ПП" in message.answers[0][0]
    user_rate_source.pop(1001, None)


@pytest.mark.asyncio
async def test_max_invoice_button_sets_mode_and_shows_hint() -> None:
    user_rate_source.pop(1001, None)
    message = FakeMessage()

    await choose_max_invoice_calculation(message)

    assert user_rate_source[1001] == MAX_INVOICE_SOURCE
    assert message.answers[0][0].startswith("💰 Максимальная сумма инвойса")
    assert "5 000 000 RUB → AED +2,7%" in message.answers[0][0]
    user_rate_source.pop(1001, None)


@pytest.mark.asyncio
async def test_max_invoice_mode_calculates_without_extra_payment() -> None:
    user_rate_source[1001] = MAX_INVOICE_SOURCE
    message = FakeMessage("5 000 000 RUB → AED +2,7%")
    cbr_service = FakeCbrService()

    try:
        await convert_currency_handler(
            message,
            cbr_service=cbr_service,
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=FakeMarketProvider(),
        )

        assert cbr_service.fetch_latest_calls == 1
        text, keyboard = message.answers[0]
        assert text.startswith("Максимальная сумма инвойса на 05.05.2026")
        assert "Лимит клиента:\n5 000 000,00 RUB" in text
        assert "1 AED = 21,3250 RUB" in text
        assert "2,7% = 2,6% + 0,1%" in text
        assert "Расчётный курс:\n21,3250 + 2,6% = 21,8795 RUB" in text
        assert "Максимальная сумма инвойса:\n228 296,12 AED" in text
        assert "228 296,12 AED × 21,8795 = 4 995 004,96 RUB" in text
        assert "Итоговая сумма:\n4 999 999,96 RUB" in text
        assert "Остаток от лимита:\n0,04 RUB" in text
        assert keyboard is not None
    finally:
        user_rate_source.pop(1001, None)


@pytest.mark.asyncio
async def test_max_invoice_mode_calculates_with_extra_payment_in_other_currency() -> None:
    user_rate_source[1001] = MAX_INVOICE_SOURCE
    message = FakeMessage("500 000 RUB → EUR +2% +215 USD ПП")
    cbr_service = FakeCbrService()

    try:
        await convert_currency_handler(
            message,
            cbr_service=cbr_service,
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=FakeMarketProvider(),
        )

        assert cbr_service.fetch_latest_calls == 1
        text, keyboard = message.answers[0]
        assert text.startswith("Максимальная сумма инвойса на 05.05.2026")
        assert "1 EUR = 88,0000 RUB" in text
        assert "1 USD = 75,0000 RUB" in text
        assert "2% + 215 USD = 1,9% + 0,1% + 215 USD" in text
        assert "Кросс-курс с учётом 215 USD:" in text
        assert "5 387,06 EUR × 88,0000 = 474 061,28 RUB" in text
        assert "215 USD × 75,0000 = 16 125,00 RUB" in text
        assert "Расчётный курс:\n90,9933 + 1,9% = 92,7222 RUB" in text
        assert "Максимальная сумма инвойса:\n5 387,06 EUR" in text
        assert "Итоговая сумма:\n499 999,55 RUB" in text
        assert "Остаток от лимита:\n0,45 RUB" in text
        assert keyboard is not None
    finally:
        user_rate_source.pop(1001, None)


@pytest.mark.asyncio
async def test_agent_cbr_mode_calculates_without_agent_word() -> None:
    user_rate_source[1001] = AGENT_CBR_SOURCE
    last_agent_calculations.pop(1001, None)
    message = FakeMessage("10000 USD +2,5%")

    try:
        await convert_currency_handler(
            message,
            cbr_service=FakeCbrService(),
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=FakeMarketProvider(),
        )

        text, keyboard = message.answers[0]
        assert text.startswith("Агентский расчёт на 05.05.2026")
        assert "Сумма инвойса:\n10 000 USD" in text
        assert "2,5% = 2,4% + 0,1%" in text
        assert "Курс в поручении" not in text
        assert "Фиксированное ПП" not in text
        assert "10 000 USD × 76,8000 = 768 000,00 RUB" in text
        assert "Итоговая сумма:\n768 768,00 RUB" in text
        assert keyboard is not None
        assert [[button.text for button in row] for row in keyboard.inline_keyboard] == [
            ["📄 Версия для поручения"],
            ["🔁 Новый расчёт", "🏠 Главное меню"],
        ]
        assert last_agent_calculations[1001].main_payment_rub == Decimal("768000")
        assert last_agent_calculations[1001].agent_fee_rub == Decimal("768")
        assert last_agent_calculations[1001].final_result == Decimal("768768")
    finally:
        user_rate_source.pop(1001, None)
        last_agent_calculations.pop(1001, None)


@pytest.mark.asyncio
async def test_agent_market_mode_calculates_cny_with_pp_without_agent_word() -> None:
    user_rate_source[1001] = AGENT_MARKET_SOURCE
    last_agent_calculations.pop(1001, None)
    message = FakeMessage("50200 CNY +2,5% +200ПП")
    market_provider = FakeMarketProvider()

    try:
        await convert_currency_handler(
            message,
            cbr_service=FakeCbrService(),
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=market_provider,
        )

        text, keyboard = message.answers[0]
        assert market_provider.requests == [["CNY"]]
        assert text.startswith("Агентский расчёт на 05.05.2026")
        assert "Сумма инвойса:\n50 200 CNY" in text
        assert "2,5% + 200 CNY = 2,4% + 0,1% + 200 CNY" in text
        assert "Курс для расчёта ПП:\n1 CNY = 10,9672 RUB" in text
        assert "Кросс-курс с учётом 200 CNY:" in text
        assert "50 200 CNY × 10,9672 = 550 553,44 RUB" in text
        assert "200 CNY × 10,9672 = 2 193,44 RUB" in text
        assert "(550 553,44 RUB + 2 193,44 RUB) / 50 200 CNY = 11,0109 RUB" in text
        assert "Расчётный курс:\n11,0109 + 2,4% = 11,2752 RUB" in text
        assert "50 200 CNY × 11,2752 = 566 015,04 RUB" in text
        assert "Платёжка" not in text
        assert "Корректировка" not in text
        assert keyboard is not None
        assert [[button.text for button in row] for row in keyboard.inline_keyboard] == [
            ["📄 Версия для поручения"],
            ["🔁 Новый расчёт", "🏠 Главное меню"],
        ]
        saved_result = last_agent_calculations[1001]
        assert saved_result.extra_payment_rub is not None
        assert saved_result.main_payment_rub == saved_result.main_currency_payment_rub
        assert saved_result.cross_rate is not None
    finally:
        user_rate_source.pop(1001, None)
        last_agent_calculations.pop(1001, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("custom_input", ["76,50 10 000 USD", "76.50 10 000 USD"])
async def test_custom_rate_mode_calculates_simple_invoice(custom_input: str) -> None:
    user_rate_source[1001] = CUSTOM_SOURCE
    message = FakeMessage(custom_input)
    cbr_service = FakeCbrService()
    market_provider = FakeMarketProvider()

    try:
        await convert_currency_handler(
            message,
            cbr_service=cbr_service,
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=market_provider,
        )

        text, keyboard = message.answers[0]
        assert cbr_service.fetch_latest_calls == 0
        assert market_provider.requests == []
        assert text.startswith("Расчёт по своему курсу на 21.07.2026")
        assert "Собственный курс:\n1 USD = 76,5000 RUB" in text
        assert "Сумма инвойса:\n10 000 USD" in text
        assert "10 000 USD × 76,5000 = 765 000,00 RUB" in text
        assert keyboard is not None
    finally:
        user_rate_source.pop(1001, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("custom_input", ["76,50 10 000 USD +2,5%", "76.50 10 000 USD +2,5%"])
async def test_agent_custom_rate_mode_calculates_without_pp(custom_input: str) -> None:
    user_rate_source[1001] = AGENT_CUSTOM_SOURCE
    last_agent_calculations.pop(1001, None)
    message = FakeMessage(custom_input)
    cbr_service = FakeCbrService()
    market_provider = FakeMarketProvider()

    try:
        await convert_currency_handler(
            message,
            cbr_service=cbr_service,
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=market_provider,
        )

        text, keyboard = message.answers[0]
        assert cbr_service.fetch_latest_calls == 0
        assert market_provider.requests == []
        assert text.startswith("Агентский расчёт по своему курсу на 21.07.2026")
        assert "Собственный курс:\n1 USD = 76,5000 RUB" in text
        assert "2,5% = 2,4% + 0,1%" in text
        assert "Расчётный курс:\n76,5000 + 2,4% = 78,3360 RUB" in text
        assert "10 000 USD × 78,3360 = 783 360,00 RUB" in text
        assert "783 360,00 RUB × 0,1% = 783,36 RUB" in text
        assert "Итоговая сумма:\n784 143,36 RUB" in text
        assert "Курс для расчёта ПП" not in text
        assert "Кросс-курс" not in text
        assert keyboard is not None
        assert last_agent_calculations[1001].adjusted_unit_rate == Decimal("78.3360")
        assert last_agent_calculations[1001].main_payment_rub == Decimal("783360.0000")
    finally:
        user_rate_source.pop(1001, None)
        last_agent_calculations.pop(1001, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "custom_input",
    ["76,50 10 000 USD +2,5% +100ПП", "76.50 10 000 USD +2,5% +100ПП"],
)
async def test_agent_custom_rate_mode_calculates_pp_without_double_commission(custom_input: str) -> None:
    user_rate_source[1001] = AGENT_CUSTOM_SOURCE
    last_agent_calculations.pop(1001, None)
    message = FakeMessage(custom_input)
    cbr_service = FakeCbrService()
    market_provider = FakeMarketProvider()

    try:
        await convert_currency_handler(
            message,
            cbr_service=cbr_service,
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=market_provider,
        )

        text, keyboard = message.answers[0]
        assert cbr_service.fetch_latest_calls == 0
        assert market_provider.requests == []
        assert text.startswith("Агентский расчёт по своему курсу на 21.07.2026")
        assert "Собственный курс:\n1 USD = 76,5000 RUB" in text
        assert "2,5% + 100 USD = 2,4% + 0,1% + 100 USD" in text
        assert "Курс для расчёта ПП:\n1 USD = 76,5000 RUB" in text
        assert "10 000 USD × 76,5000 = 765 000,00 RUB" in text
        assert "100 USD × 76,5000 = 7 650,00 RUB" in text
        assert "100 USD × 78,3360" not in text
        assert "(765 000,00 RUB + 7 650,00 RUB) / 10 000 USD = 77,2650 RUB" in text
        assert "Расчётный курс:\n77,2650 + 2,4% = 79,1194 RUB" in text
        assert "10 000 USD × 79,1194 = 791 194,00 RUB" in text
        assert "791 194,00 RUB × 0,1% = 791,19 RUB" in text
        assert "Итоговая сумма:\n791 985,19 RUB" in text
        assert keyboard is not None
        saved_result = last_agent_calculations[1001]
        assert saved_result.adjusted_extra_payment_unit_rate == Decimal("76.50")
        assert saved_result.adjusted_unit_rate == Decimal("79.1194")
        assert saved_result.main_payment_rub == Decimal("791194.0000")
        assert saved_result.agent_fee_rub == Decimal("791.19400")
        assert saved_result.final_result == Decimal("791985.19400")
    finally:
        user_rate_source.pop(1001, None)
        last_agent_calculations.pop(1001, None)


def test_format_agent_assignment_text_uses_amounts_and_words() -> None:
    request = parse_convert_request("10000 USD +2,5% +100ПП")
    assert request is not None
    snapshot = FakeCbrService()._snapshot()
    result = convert_agent_calculation(request, snapshot)
    assert result is not None

    text = format_agent_assignment_text(result)

    assert text == (
        "Версия для поручения:\n"
        "\n"
        "Курс в поручении:\n"
        "1 USD = 77,5680 RUB\n"
        "\n"
        "Основной платёж:\n"
        "775 680,00 RUB\n"
        "Семьсот семьдесят пять тысяч шестьсот восемьдесят рублей 00 копеек\n"
        "\n"
        "Агентское вознаграждение:\n"
        "775,68 RUB\n"
        "Семьсот семьдесят пять рублей 68 копеек\n"
        "\n"
        "Итоговая сумма:\n"
        "776 455,68 RUB\n"
        "Семьсот семьдесят шесть тысяч четыреста пятьдесят пять рублей 68 копеек"
    )
    assert "Доп. платёж" not in text
    assert "ПП" not in text
    assert "Платёжка" not in text


@pytest.mark.asyncio
async def test_agent_assignment_callback_returns_last_agent_calculation_text() -> None:
    request = parse_convert_request("10000 USD +2,5% +100ПП")
    assert request is not None
    result = convert_agent_calculation(request, FakeCbrService()._snapshot())
    assert result is not None
    last_agent_calculations[1001] = result
    callback = FakeCallback()

    try:
        await show_agent_assignment_text(callback)

        assert callback.answered is True
        assert callback.message.answers == [(format_agent_assignment_text(result), None)]
    finally:
        last_agent_calculations.pop(1001, None)


def test_agent_assignment_text_without_last_calculation_shows_hint() -> None:
    last_agent_calculations.pop(404, None)

    text = get_agent_assignment_text_for_user(404)

    assert text == (
        "Сначала выполните агентский расчёт, например:\n"
        "\n"
        "10 000 USD +2,5%\n"
        "50 200 CNY +2,5% +200ПП"
    )


@pytest.mark.asyncio
async def test_explicit_agent_reverse_direction_shows_agent_error() -> None:
    message = FakeMessage("1 000 000 RUB в USD агент +2,5%")

    await convert_currency_handler(
        message,
        cbr_service=FakeCbrService(),
        app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
        market_rate_provider=FakeMarketProvider(),
    )

    assert message.answers[0][0] == AGENT_REVERSE_UNSUPPORTED_TEXT


@pytest.mark.asyncio
async def test_agent_rate_must_be_more_than_fee() -> None:
    user_rate_source[1001] = AGENT_CBR_SOURCE
    message = FakeMessage("10000 USD +0,1%")

    try:
        await convert_currency_handler(
            message,
            cbr_service=FakeCbrService(),
            app_config=Settings(bot_token="123:test", timezone="Europe/Moscow"),
            market_rate_provider=FakeMarketProvider(),
        )
    finally:
        user_rate_source.pop(1001, None)

    assert message.answers[0][0] == AGENT_RATE_TOO_LOW_TEXT
