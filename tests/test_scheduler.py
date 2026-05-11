from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from db.models import UserSettings
from services.cbr import CurrencyRate, RatesSnapshot
from services.scheduler import (
    DAILY_RETRY_DELAY_MINUTES,
    calculate_cbr_rate_change,
    cbr_update_notification_keyboard,
    check_cbr_update_notifications,
    format_cbr_update_notification,
    get_previous_cbr_rates,
    send_daily_rates,
)


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.messages: list[tuple[int, str, object | None]] = []
        self.error = error

    async def send_message(self, telegram_id: int, text: str, reply_markup=None) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append((telegram_id, text, reply_markup))


class FakeRepo:
    def __init__(self, users: list[UserSettings]) -> None:
        self.users = users
        self.sent: list[tuple[int, date]] = []
        self.disabled: list[int] = []

    def get_daily_users(self) -> list[UserSettings]:
        return self.users

    def was_daily_sent(self, telegram_id: int, rate_date: date) -> bool:
        return (telegram_id, rate_date) in self.sent

    def mark_daily_sent(self, telegram_id: int, rate_date: date) -> None:
        self.sent.append((telegram_id, rate_date))

    def get_cbr_update_notification_users(self) -> list[UserSettings]:
        return [user for user in self.users if user.cbr_update_notifications]

    def mark_cbr_update_notification_sent(self, telegram_id: int, rate_date: date) -> None:
        self.sent.append((telegram_id, rate_date))
        self.users = [
            UserSettings(
                telegram_id=user.telegram_id,
                mode=user.mode,
                daily_time=user.daily_time,
                timezone=user.timezone,
                currencies=user.currencies,
                cbr_update_notifications=user.cbr_update_notifications,
                last_sent_cbr_date=rate_date if user.telegram_id == telegram_id else user.last_sent_cbr_date,
            )
            for user in self.users
        ]

    def set_cbr_update_notifications(self, telegram_id: int, enabled: bool) -> UserSettings:
        self.disabled.append(telegram_id)
        return UserSettings(telegram_id=telegram_id, cbr_update_notifications=enabled)


class FakeCBRService:
    def __init__(self, snapshot: RatesSnapshot | None = None, error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.error = error

    async def get_rates_with_delta(self, target_date: date) -> RatesSnapshot:
        if self.error is not None:
            raise self.error
        assert self.snapshot is not None
        return self.snapshot

    async def fetch_rates(self, target_date: date) -> RatesSnapshot:
        if self.error is not None:
            raise self.error
        assert self.snapshot is not None
        return self.snapshot


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    def add_job(self, *args, **kwargs) -> None:
        self.jobs.append({"args": args, "kwargs": kwargs})


def make_snapshot(rate_date: date) -> RatesSnapshot:
    return RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate(
                code="USD",
                name="Доллар США",
                nominal=1,
                value=Decimal("75.5273"),
                unit_rate=Decimal("75.5273"),
                date=rate_date,
            ),
            "EUR": CurrencyRate(
                code="EUR",
                name="Евро",
                nominal=1,
                value=Decimal("88.2826"),
                unit_rate=Decimal("88.2826"),
                date=rate_date,
            ),
        },
        deltas={"USD": Decimal("0.69"), "EUR": Decimal("0.76")},
    )


def make_full_snapshot(rate_date: date) -> RatesSnapshot:
    rates = {
        "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.1234"), Decimal("75.1234"), rate_date),
        "EUR": CurrencyRate("EUR", "Евро", 1, Decimal("86.4321"), Decimal("86.4321"), rate_date),
        "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("10.4321"), Decimal("10.4321"), rate_date),
        "GBP": CurrencyRate("GBP", "Фунт стерлингов", 1, Decimal("101.1234"), Decimal("101.1234"), rate_date),
        "AED": CurrencyRate("AED", "Дирхам ОАЭ", 1, Decimal("20.4512"), Decimal("20.4512"), rate_date),
        "THB": CurrencyRate("THB", "Бат", 1, Decimal("2.3042"), Decimal("2.3042"), rate_date),
        "KRW": CurrencyRate("KRW", "Вона", 1, Decimal("0.0508"), Decimal("0.0508"), rate_date),
        "JPY": CurrencyRate("JPY", "Иена", 1, Decimal("0.4728"), Decimal("0.4728"), rate_date),
    }
    return RatesSnapshot(date=rate_date, rates=rates)


def make_comparison_current_snapshot() -> RatesSnapshot:
    rate_date = date(2026, 5, 6)
    rates = {
        "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.4388"), Decimal("75.4388"), rate_date),
        "EUR": CurrencyRate("EUR", "Евро", 1, Decimal("88.2651"), Decimal("88.2651"), rate_date),
        "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("11.0343"), Decimal("11.0343"), rate_date),
        "GBP": CurrencyRate("GBP", "Фунт стерлингов", 1, Decimal("102.4610"), Decimal("102.4610"), rate_date),
        "AED": CurrencyRate("AED", "Дирхам ОАЭ", 1, Decimal("20.5415"), Decimal("20.5415"), rate_date),
        "THB": CurrencyRate("THB", "Бат", 1, Decimal("2.3021"), Decimal("2.3021"), rate_date),
        "KRW": CurrencyRate("KRW", "Вона", 1000, Decimal("50.8000"), Decimal("0.0508"), rate_date),
        "JPY": CurrencyRate("JPY", "Иена", 100, Decimal("48.0000"), Decimal("0.4800"), rate_date),
    }
    return RatesSnapshot(date=rate_date, rates=rates)


def make_comparison_previous_snapshot() -> RatesSnapshot:
    rate_date = date(2026, 5, 5)
    rates = {
        "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0157"), Decimal("75.0157"), rate_date),
        "EUR": CurrencyRate("EUR", "Евро", 1, Decimal("88.4755"), Decimal("88.4755"), rate_date),
        "CNY": CurrencyRate("CNY", "Китайский юань", 1, Decimal("11.0193"), Decimal("11.0193"), rate_date),
        "GBP": CurrencyRate("GBP", "Фунт стерлингов", 1, Decimal("102.7610"), Decimal("102.7610"), rate_date),
        "AED": CurrencyRate("AED", "Дирхам ОАЭ", 1, Decimal("20.4295"), Decimal("20.4295"), rate_date),
        "THB": CurrencyRate("THB", "Бат", 1, Decimal("2.3061"), Decimal("2.3061"), rate_date),
        "KRW": CurrencyRate("KRW", "Вона", 1000, Decimal("50.7000"), Decimal("0.0507"), rate_date),
        "JPY": CurrencyRate("JPY", "Иена", 100, Decimal("48.3200"), Decimal("0.4832"), rate_date),
    }
    return RatesSnapshot(date=rate_date, rates=rates)


@pytest.mark.asyncio
async def test_send_daily_rates_sends_only_selected_currencies_to_daily_users() -> None:
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    bot = FakeBot()
    repo = FakeRepo(
        [
            UserSettings(telegram_id=1, mode="daily", currencies=["USD"]),
            UserSettings(telegram_id=2, mode="daily", currencies=[]),
        ]
    )

    await send_daily_rates(
        bot=bot,
        repo=repo,
        cbr_service=FakeCBRService(make_snapshot(today)),
        scheduler=FakeScheduler(),
        timezone_name="Europe/Moscow",
    )

    assert len(bot.messages) == 1
    assert bot.messages[0][0] == 1
    assert "Курс USD к RUB" in bot.messages[0][1]
    assert "Курс EUR к RUB" not in bot.messages[0][1]
    assert repo.sent == [(1, today)]


@pytest.mark.asyncio
async def test_send_daily_rates_retries_when_cbr_date_is_not_today() -> None:
    today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    scheduler = FakeScheduler()

    await send_daily_rates(
        bot=FakeBot(),
        repo=FakeRepo([UserSettings(telegram_id=1, mode="daily", currencies=["USD"])]),
        cbr_service=FakeCBRService(make_snapshot(today - timedelta(days=1))),
        scheduler=scheduler,
        timezone_name="Europe/Moscow",
    )

    assert len(scheduler.jobs) == 1
    retry_kwargs = scheduler.jobs[0]["kwargs"]["kwargs"]
    assert retry_kwargs["retry_delay_minutes"] == DAILY_RETRY_DELAY_MINUTES
    assert retry_kwargs["retry_count"] == 1


def test_format_cbr_update_notification_with_changes() -> None:
    message = format_cbr_update_notification(make_comparison_current_snapshot(), make_comparison_previous_snapshot())

    assert message == (
        "📊 Курсы ЦБ РФ обновлены\n"
        "\n"
        "Дата курса:\n"
        "06.05.2026\n"
        "\n"
        "Сравнение с:\n"
        "05.05.2026\n"
        "\n"
        "USD — Доллар США\n"
        "1 USD = 75,4388 RUB\n"
        "Изменение: +0,4231 RUB / +0,56%\n"
        "Курс вырос 📈\n"
        "\n"
        "EUR — Евро\n"
        "1 EUR = 88,2651 RUB\n"
        "Изменение: -0,2104 RUB / -0,24%\n"
        "Курс снизился 📉\n"
        "\n"
        "CNY — Китайский юань\n"
        "1 CNY = 11,0343 RUB\n"
        "Изменение: +0,0150 RUB / +0,14%\n"
        "Курс вырос 📈\n"
        "\n"
        "GBP — Фунт стерлингов\n"
        "1 GBP = 102,4610 RUB\n"
        "Изменение: -0,3000 RUB / -0,29%\n"
        "Курс снизился 📉\n"
        "\n"
        "AED — Дирхам ОАЭ\n"
        "1 AED = 20,5415 RUB\n"
        "Изменение: +0,1120 RUB / +0,55%\n"
        "Курс вырос 📈\n"
        "\n"
        "THB — Тайский бат\n"
        "1 THB = 2,3021 RUB\n"
        "Изменение: -0,0040 RUB / -0,17%\n"
        "Курс снизился 📉\n"
        "\n"
        "KRW — Южнокорейская вона\n"
        "1 KRW = 0,0508 RUB\n"
        "Изменение: +0,0001 RUB / +0,20%\n"
        "Курс вырос 📈\n"
        "\n"
        "JPY — Японская иена\n"
        "1 JPY = 0,4800 RUB\n"
        "Изменение: -0,0032 RUB / -0,66%\n"
        "Курс снизился 📉"
    )


def test_format_cbr_update_notification_without_previous_rates() -> None:
    message = format_cbr_update_notification(make_full_snapshot(date(2026, 5, 6)))

    assert "Не удалось получить предыдущий курс для сравнения." in message
    assert "Сравнение с:" not in message
    assert "USD — Доллар США\n1 USD = 75,1234 RUB" in message
    assert "Изменение:" not in message


def test_format_cbr_update_notification_omits_change_for_missing_previous_currency() -> None:
    current = make_comparison_current_snapshot()
    previous = RatesSnapshot(
        date=date(2026, 5, 5),
        rates={
            "USD": make_comparison_previous_snapshot().rates["USD"],
        },
    )

    message = format_cbr_update_notification(current, previous)

    assert "USD — Доллар США\n1 USD = 75,4388 RUB\nИзменение: +0,4231 RUB / +0,56%" in message
    assert "EUR — Евро\n1 EUR = 88,2651 RUB\n\nCNY" in message


def test_calculate_cbr_rate_change_uses_unit_rate_for_jpy_and_krw() -> None:
    current = make_comparison_current_snapshot()
    previous = make_comparison_previous_snapshot()

    jpy_change = calculate_cbr_rate_change(current.rates["JPY"], previous.rates["JPY"])
    krw_change = calculate_cbr_rate_change(current.rates["KRW"], previous.rates["KRW"])

    assert jpy_change is not None
    assert jpy_change.delta_rub == Decimal("-0.0032")
    assert jpy_change.delta_percent.quantize(Decimal("0.01")) == Decimal("-0.66")
    assert krw_change is not None
    assert krw_change.delta_rub == Decimal("0.0001")
    assert krw_change.delta_percent.quantize(Decimal("0.01")) == Decimal("0.20")


def test_format_cbr_update_notification_shows_zero_change() -> None:
    rate_date = date(2026, 5, 6)
    previous_date = date(2026, 5, 5)
    current = RatesSnapshot(
        date=rate_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), rate_date),
        },
    )
    previous = RatesSnapshot(
        date=previous_date,
        rates={
            "USD": CurrencyRate("USD", "Доллар США", 1, Decimal("75.0000"), Decimal("75.0000"), previous_date),
        },
    )

    message = format_cbr_update_notification(current, previous)

    assert "Изменение: 0,0000 RUB / 0,00%" in message
    assert "Курс не изменился ➖" in message


class PreviousSearchCBRService:
    def __init__(self) -> None:
        self.calls: list[date] = []

    async def fetch_rates(self, target_date: date) -> RatesSnapshot:
        self.calls.append(target_date)
        if target_date >= date(2026, 5, 9):
            return make_full_snapshot(date(2026, 5, 12))
        return make_full_snapshot(date(2026, 5, 8))


@pytest.mark.asyncio
async def test_get_previous_cbr_rates_finds_previous_available_published_date() -> None:
    service = PreviousSearchCBRService()

    previous = await get_previous_cbr_rates(service, date(2026, 5, 12))

    assert previous is not None
    assert previous.date == date(2026, 5, 8)
    assert service.calls == [
        date(2026, 5, 11),
        date(2026, 5, 10),
        date(2026, 5, 9),
        date(2026, 5, 8),
    ]


def test_cbr_update_notification_keyboard() -> None:
    keyboard = cbr_update_notification_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("📊 Курс ЦБ РФ", "cbr:menu"),
        ("🧮 Расчёт по ЦБ РФ", "calc:cbr"),
        ("🏠 Главное меню", "main_menu"),
    ]


@pytest.mark.asyncio
async def test_cbr_update_notification_sends_new_date_once() -> None:
    now = datetime(2026, 5, 5, 17, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    rate_date = date(2026, 5, 6)
    bot = FakeBot()
    repo = FakeRepo([UserSettings(telegram_id=1, cbr_update_notifications=True)])

    await check_cbr_update_notifications(
        bot=bot,
        repo=repo,
        cbr_service=FakeCBRService(make_full_snapshot(rate_date)),
        timezone_name="Europe/Moscow",
        now=now,
    )
    await check_cbr_update_notifications(
        bot=bot,
        repo=repo,
        cbr_service=FakeCBRService(make_full_snapshot(rate_date)),
        timezone_name="Europe/Moscow",
        now=now,
    )

    assert len(bot.messages) == 1
    assert bot.messages[0][0] == 1
    assert "📊 Курсы ЦБ РФ обновлены" in bot.messages[0][1]
    assert repo.sent == [(1, rate_date)]


@pytest.mark.asyncio
async def test_cbr_update_notification_sends_when_date_is_new() -> None:
    now = datetime(2026, 5, 5, 17, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    repo = FakeRepo(
        [
            UserSettings(
                telegram_id=1,
                cbr_update_notifications=True,
                last_sent_cbr_date=date(2026, 5, 5),
            )
        ]
    )
    bot = FakeBot()

    await check_cbr_update_notifications(
        bot=bot,
        repo=repo,
        cbr_service=FakeCBRService(make_full_snapshot(date(2026, 5, 6))),
        timezone_name="Europe/Moscow",
        now=now,
    )

    assert len(bot.messages) == 1
    assert repo.sent == [(1, date(2026, 5, 6))]


@pytest.mark.asyncio
async def test_cbr_update_notification_skips_when_cbr_has_not_published_target_date() -> None:
    now = datetime(2026, 5, 5, 17, 0, tzinfo=ZoneInfo("Europe/Moscow"))
    bot = FakeBot()
    repo = FakeRepo([UserSettings(telegram_id=1, cbr_update_notifications=True)])

    await check_cbr_update_notifications(
        bot=bot,
        repo=repo,
        cbr_service=FakeCBRService(make_full_snapshot(date(2026, 5, 5))),
        timezone_name="Europe/Moscow",
        now=now,
    )

    assert bot.messages == []
    assert repo.sent == []


@pytest.mark.asyncio
async def test_cbr_update_notification_does_not_crash_on_cbr_error() -> None:
    await check_cbr_update_notifications(
        bot=FakeBot(),
        repo=FakeRepo([UserSettings(telegram_id=1, cbr_update_notifications=True)]),
        cbr_service=FakeCBRService(error=RuntimeError("CBR down")),
        timezone_name="Europe/Moscow",
        now=datetime(2026, 5, 5, 17, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )


@pytest.mark.asyncio
async def test_cbr_update_notification_does_not_crash_on_telegram_error() -> None:
    repo = FakeRepo([UserSettings(telegram_id=1, cbr_update_notifications=True)])

    await check_cbr_update_notifications(
        bot=FakeBot(error=RuntimeError("Telegram down")),
        repo=repo,
        cbr_service=FakeCBRService(make_full_snapshot(date(2026, 5, 6))),
        timezone_name="Europe/Moscow",
        now=datetime(2026, 5, 5, 17, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )

    assert repo.sent == []
