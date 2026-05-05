from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from db.models import UserSettings
from services.cbr import CurrencyRate, RatesSnapshot
from services.scheduler import (
    DAILY_RETRY_DELAY_MINUTES,
    cbr_update_notification_keyboard,
    check_cbr_update_notifications,
    format_cbr_update_notification,
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


def test_format_cbr_update_notification() -> None:
    message = format_cbr_update_notification(make_full_snapshot(date(2026, 5, 6)))

    assert message == (
        "📊 Курсы ЦБ РФ обновлены\n"
        "\n"
        "Дата курса:\n"
        "06.05.2026\n"
        "\n"
        "USD:\n"
        "1 USD = 75,1234\n"
        "\n"
        "EUR:\n"
        "1 EUR = 86,4321\n"
        "\n"
        "CNY:\n"
        "1 CNY = 10,4321\n"
        "\n"
        "GBP:\n"
        "1 GBP = 101,1234\n"
        "\n"
        "AED:\n"
        "1 AED = 20,4512\n"
        "\n"
        "THB:\n"
        "1 THB = 2,3042\n"
        "\n"
        "KRW:\n"
        "1 KRW = 0,0508\n"
        "\n"
        "JPY:\n"
        "1 JPY = 0,4728"
    )


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
