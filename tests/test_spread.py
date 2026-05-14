from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from config import Settings
from core.models import CurrencyRate, RatesSnapshot
from handlers.rates import CBR_SPREAD_UNAVAILABLE_TEXT, answer_spread, refresh_spread, spread_after_rates_keyboard
from services.cbr import CBRServiceError
from services.rates.cbr import rates_from_snapshot
from services.rates.market import MARKET_UNAVAILABLE_TEXT, MarketRate, MarketRateProviderError
from services.rates.spread import SPREAD_RATE_ORDER, calculate_spread, format_spread_message


def make_settings() -> Settings:
    return Settings(bot_token="123:test", timezone="Europe/Moscow")


def make_snapshot() -> RatesSnapshot:
    rate_date = date(2026, 5, 5)
    return RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.4388"), Decimal("75.4388"), rate_date),
            "AED": CurrencyRate("AED", "Дирхам ОАЭ", 1, Decimal("20.5415"), Decimal("20.5415"), rate_date),
            "EUR": CurrencyRate("EUR", "Евро", 1, Decimal("88.2651"), Decimal("88.2651"), rate_date),
            "CNY": CurrencyRate("CNY", "Юань", 1, Decimal("11.0343"), Decimal("11.0343"), rate_date),
        },
    )


def make_market_rates() -> dict[str, MarketRate]:
    fetched_at = datetime(2026, 5, 5, 23, 45)
    return {
        "USD": MarketRate("USD", "USD/RUB", Decimal("74.8850"), "Yahoo Finance — рыночный ориентир", fetched_at),
        "AED": MarketRate("AED", "AED/RUB", Decimal("20.3935"), "Yahoo Finance — рыночный ориентир", fetched_at),
        "EUR": MarketRate("EUR", "EUR/RUB", Decimal("87.8310"), "Yahoo Finance — рыночный ориентир", fetched_at),
        "CNY": MarketRate("CNY", "CNY/RUB", Decimal("10.9672"), "Yahoo Finance — рыночный ориентир", fetched_at),
    }


def test_calculate_spread_for_usd_aed_cny_eur_in_expected_order() -> None:
    cbr_rates = rates_from_snapshot(make_snapshot(), fetched_at=datetime(2026, 5, 5, 23, 45))
    spreads = calculate_spread(cbr_rates, make_market_rates())

    by_code = {spread.code: spread for spread in spreads}

    assert tuple(by_code) == SPREAD_RATE_ORDER
    assert SPREAD_RATE_ORDER == ("USD", "AED", "CNY", "EUR")
    assert by_code["USD"].difference == Decimal("-0.5538")
    assert by_code["USD"].percent.quantize(Decimal("0.01")) == Decimal("-0.73")
    assert by_code["AED"].difference == Decimal("-0.1480")
    assert by_code["AED"].percent.quantize(Decimal("0.01")) == Decimal("-0.72")
    assert by_code["EUR"].difference == Decimal("-0.4341")
    assert by_code["EUR"].percent.quantize(Decimal("0.01")) == Decimal("-0.49")
    assert by_code["CNY"].difference == Decimal("-0.0671")
    assert by_code["CNY"].percent.quantize(Decimal("0.01")) == Decimal("-0.61")


def test_format_spread_message_shows_negative_spread_with_minus() -> None:
    cbr_rates = rates_from_snapshot(make_snapshot(), fetched_at=datetime(2026, 5, 5, 23, 45))
    message = format_spread_message(calculate_spread(cbr_rates, make_market_rates()))

    assert "📉 Спред ЦБ РФ / рынок" in message
    assert (
        "USD/RUB — Доллар США\n"
        "ЦБ РФ: 75,4388\n"
        "Рынок: 74,8850\n"
        "Разница: -0,5538\n"
        "Спред: -0,73%"
    ) in message
    assert (
        "AED/RUB — Дирхам ОАЭ\n"
        "ЦБ РФ: 20,5415\n"
        "Рынок: 20,3935\n"
        "Разница: -0,1480\n"
        "Спред: -0,72%"
    ) in message
    assert message.index("USD/RUB") < message.index("AED/RUB") < message.index("CNY/RUB") < message.index("EUR/RUB")
    assert "<code>" not in message
    assert "</code>" not in message
    assert "Обновлено:\n23:45 МСК" in message
    assert "₽" not in message


def test_format_spread_message_shows_positive_spread_with_plus() -> None:
    snapshot = make_snapshot()
    cbr_rates = rates_from_snapshot(snapshot, fetched_at=datetime(2026, 5, 5, 23, 45))
    market_rates = make_market_rates()
    market_rates["USD"] = MarketRate(
        "USD",
        "USD/RUB",
        Decimal("76.4388"),
        "Yahoo Finance — рыночный ориентир",
        datetime(2026, 5, 5, 23, 45),
    )

    message = format_spread_message(calculate_spread(cbr_rates, market_rates, ("USD",)))

    assert "Разница: +1,0000" in message
    assert "Спред: +1,33%" in message


def test_spread_keyboard_has_refresh_and_menu() -> None:
    keyboard = spread_after_rates_keyboard()
    buttons = [(button.text, button.callback_data) for row in keyboard.inline_keyboard for button in row]

    assert buttons == [
        ("🔄 Обновить спред", "spread:refresh"),
        ("🏠 Главное меню", "main_menu"),
    ]


class FakeCbrService:
    def __init__(self, snapshot: RatesSnapshot | None = None, error: Exception | None = None) -> None:
        self.snapshot = snapshot or make_snapshot()
        self.error = error

    async def fetch_rates(self, target_date):
        if self.error is not None:
            raise self.error
        return self.snapshot

    async def get_latest_cbr_rates(self):
        if self.error is not None:
            raise self.error
        return self.snapshot

    async def fetch_latest_rates(self):
        return await self.get_latest_cbr_rates()


class FakeMarketProvider:
    def __init__(self, rates: dict[str, MarketRate] | None = None, error: Exception | None = None) -> None:
        self.rates = rates or make_market_rates()
        self.error = error
        self.requested_codes: list[str] | None = None

    async def get_rates(self, codes: list[str]) -> dict[str, MarketRate]:
        self.requested_codes = codes
        if self.error is not None:
            raise self.error
        return self.rates


class FakeMessage:
    def __init__(self) -> None:
        self.answers: list[dict[str, object]] = []

    async def answer(self, text: str, reply_markup=None, parse_mode=None) -> None:
        self.answers.append({"text": text, "reply_markup": reply_markup, "parse_mode": parse_mode})


class FakeCallback:
    def __init__(self) -> None:
        self.message = FakeMessage()
        self.from_user = SimpleNamespace(id=1001)
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


@pytest.mark.asyncio
async def test_answer_spread_sends_html_message_with_refresh_button() -> None:
    message = FakeMessage()
    market_provider = FakeMarketProvider()

    await answer_spread(message, FakeCbrService(), make_settings(), market_provider)

    assert market_provider.requested_codes == ["USD", "AED", "CNY", "EUR"]
    assert message.answers[0]["parse_mode"] is None
    assert "📉 Спред ЦБ РФ / рынок" in message.answers[0]["text"]
    assert message.answers[0]["reply_markup"] is not None


@pytest.mark.asyncio
async def test_answer_spread_shows_market_error_when_market_provider_unavailable() -> None:
    message = FakeMessage()

    await answer_spread(
        message,
        FakeCbrService(),
        make_settings(),
        FakeMarketProvider(error=MarketRateProviderError()),
    )

    assert message.answers == [{"text": MARKET_UNAVAILABLE_TEXT, "reply_markup": None, "parse_mode": None}]


@pytest.mark.asyncio
async def test_answer_spread_shows_cbr_error_when_cbr_unavailable() -> None:
    message = FakeMessage()

    await answer_spread(
        message,
        FakeCbrService(error=CBRServiceError("boom")),
        make_settings(),
        FakeMarketProvider(),
    )

    assert message.answers == [{"text": CBR_SPREAD_UNAVAILABLE_TEXT, "reply_markup": None, "parse_mode": None}]


@pytest.mark.asyncio
async def test_refresh_spread_callback_recalculates_spread() -> None:
    callback = FakeCallback()

    await refresh_spread(callback, FakeCbrService(), make_settings(), FakeMarketProvider())

    assert callback.answered is True
    assert "📉 Спред ЦБ РФ / рынок" in callback.message.answers[0]["text"]
