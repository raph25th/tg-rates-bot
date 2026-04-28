from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from db.models import UserSettings
from services.cbr import CurrencyRate, RatesSnapshot
from services.scheduler import DAILY_RETRY_DELAY_MINUTES, send_daily_rates


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, telegram_id: int, text: str) -> None:
        self.messages.append((telegram_id, text))


class FakeRepo:
    def __init__(self, users: list[UserSettings]) -> None:
        self.users = users
        self.sent: list[tuple[int, date]] = []

    def get_daily_users(self) -> list[UserSettings]:
        return self.users

    def was_daily_sent(self, telegram_id: int, rate_date: date) -> bool:
        return (telegram_id, rate_date) in self.sent

    def mark_daily_sent(self, telegram_id: int, rate_date: date) -> None:
        self.sent.append((telegram_id, rate_date))


class FakeCBRService:
    def __init__(self, snapshot: RatesSnapshot) -> None:
        self.snapshot = snapshot

    async def get_rates_with_delta(self, target_date: date) -> RatesSnapshot:
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
