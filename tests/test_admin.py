from datetime import datetime
from types import SimpleNamespace

import pytest

from config import Settings, parse_admin_telegram_ids, parse_owner_telegram_id
from db.models import AdminUserRow, BotStats
from handlers.admin import ACCESS_DENIED_TEXT, format_users, format_users_report, show_stats, show_users


class FakeRepo:
    def __init__(self) -> None:
        self.stats = BotStats(
            total_users=13,
            cbr_update_notifications=3,
            new_24h=2,
            new_7d=5,
        )
        self.users = [
            AdminUserRow(
                telegram_id=762498021,
                username="alice",
                first_name="Alice",
                last_name="Smith",
                cbr_update_notifications=True,
                created_at=datetime(2026, 5, 15, 10, 0),
                updated_at=datetime(2026, 5, 15, 14, 15),
            ),
            AdminUserRow(
                telegram_id=7781558647,
                username=None,
                first_name="Иван",
                last_name=None,
                cbr_update_notifications=False,
                created_at=datetime(2026, 5, 14, 19, 0),
                updated_at=datetime(2026, 5, 14, 20, 0),
            ),
        ]
        self.stats_called = False
        self.users_called = False

    def get_bot_stats(self) -> BotStats:
        self.stats_called = True
        return self.stats

    def list_admin_users(self, limit: int = 30) -> list[AdminUserRow]:
        self.users_called = True
        assert limit == 30
        return self.users


class FakeMessage:
    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.answers: list[str] = []

    async def answer(self, text: str) -> None:
        self.answers.append(text)


def test_parse_admin_telegram_ids() -> None:
    assert parse_admin_telegram_ids("") == ()
    assert parse_admin_telegram_ids("762498021, 123456789") == (762498021, 123456789)


def test_parse_owner_telegram_id() -> None:
    assert parse_owner_telegram_id("") is None
    assert parse_owner_telegram_id("762498021") == 762498021


@pytest.mark.asyncio
async def test_stats_available_for_admin() -> None:
    repo = FakeRepo()
    message = FakeMessage(762498021)
    settings = Settings(bot_token="123:test", admin_telegram_ids=(762498021,))

    await show_stats(message, repo, settings)

    assert repo.stats_called is True
    assert message.answers == [
        "Статистика бота:\n"
        "\n"
        "Всего пользователей: 13\n"
        "С уведомлениями ЦБ: 3\n"
        "\n"
        "Новых за 24 часа: 2\n"
        "Новых за 7 дней: 5"
    ]


@pytest.mark.asyncio
async def test_stats_unavailable_for_non_admin() -> None:
    repo = FakeRepo()
    message = FakeMessage(1)
    settings = Settings(bot_token="123:test", admin_telegram_ids=(762498021,))

    await show_stats(message, repo, settings)

    assert repo.stats_called is False
    assert message.answers == [ACCESS_DENIED_TEXT]


@pytest.mark.asyncio
async def test_users_available_for_owner() -> None:
    repo = FakeRepo()
    message = FakeMessage(762498021)
    settings = Settings(bot_token="123:test", owner_telegram_id=762498021)

    await show_users(message, repo, settings)

    assert repo.users_called is True
    assert message.answers == [
        "Пользователи бота:\n"
        "\n"
        "Всего: 13\n"
        "С уведомлениями ЦБ: 3\n"
        "\n"
        "Последние пользователи:\n"
        "\n"
        "1. 762498021\n"
        "@alice\n"
        "Alice Smith\n"
        "Обновлён: 15.05.2026 14:15\n"
        "\n"
        "2. 7781558647\n"
        "без username\n"
        "Иван\n"
        "Обновлён: 14.05.2026 20:00"
    ]


@pytest.mark.asyncio
async def test_users_unavailable_for_non_owner() -> None:
    repo = FakeRepo()
    message = FakeMessage(1)
    settings = Settings(bot_token="123:test", owner_telegram_id=762498021)

    await show_users(message, repo, settings)

    assert repo.users_called is False
    assert message.answers == [ACCESS_DENIED_TEXT]


@pytest.mark.asyncio
async def test_users_unavailable_when_owner_is_not_configured() -> None:
    repo = FakeRepo()
    message = FakeMessage(762498021)
    settings = Settings(bot_token="123:test", owner_telegram_id=None)

    await show_users(message, repo, settings)

    assert repo.users_called is False
    assert message.answers == [ACCESS_DENIED_TEXT]


def test_format_users_shows_username_and_missing_username() -> None:
    repo = FakeRepo()

    text = format_users(repo.users)

    assert "@alice" in text
    assert "без username" in text
    assert "Alice Smith" in text
    assert "Иван" in text


def test_format_users_report_includes_stats() -> None:
    repo = FakeRepo()

    text = format_users_report(repo.stats, repo.users)

    assert "Всего: 13" in text
    assert "С уведомлениями ЦБ: 3" in text
    assert "Последние пользователи:" in text
