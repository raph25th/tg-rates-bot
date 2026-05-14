import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from db.repo import UserRepository
from handlers.start import start_handler
from main import UserProfileMiddleware


def make_repo() -> UserRepository:
    database_dir = Path(".test_dbs")
    database_dir.mkdir(parents=True, exist_ok=True)
    repo = UserRepository(database_path=str(database_dir / f"{uuid4().hex}.db"))
    repo.init()
    return repo


def cleanup_repo(repo: UserRepository) -> None:
    database_path = Path(repo.database_path)
    for path in (
        database_path,
        database_path.with_name(f"{database_path.name}-wal"),
        database_path.with_name(f"{database_path.name}-shm"),
    ):
        if path.exists():
            try:
                path.unlink()
            except PermissionError:
                pass


class FakeMessage:
    def __init__(
        self,
        *,
        telegram_id: int = 1001,
        username: str | None = "alice",
        first_name: str | None = "Alice",
        last_name: str | None = "Smith",
    ) -> None:
        self.from_user = SimpleNamespace(
            id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self.answers: list[tuple[str, object | None]] = []

    async def answer(self, text: str, reply_markup=None) -> None:
        self.answers.append((text, reply_markup))


def test_user_profile_columns_are_added_to_existing_users_table() -> None:
    database_dir = Path(".test_dbs")
    database_dir.mkdir(parents=True, exist_ok=True)
    database_path = database_dir / f"{uuid4().hex}.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                telegram_id INTEGER PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'manual',
                daily_time TEXT NOT NULL DEFAULT '18:10',
                timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("INSERT INTO users (telegram_id, mode) VALUES (1001, 'daily')")

    repo = UserRepository(database_path=str(database_path))
    try:
        repo.init()
        with sqlite3.connect(database_path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()}

        settings = repo.get_user_settings(1001)

        assert {"username", "first_name", "last_name"}.issubset(columns)
        assert settings.telegram_id == 1001
        assert settings.mode == "daily"
        assert settings.username is None
        assert settings.first_name is None
        assert settings.last_name is None
    finally:
        cleanup_repo(repo)


def test_user_profile_migration_can_run_twice() -> None:
    repo = make_repo()
    try:
        repo.init()
        repo.init()

        settings = repo.update_user_profile(1001, "alice", "Alice", "Smith")

        assert settings.username == "alice"
        assert settings.first_name == "Alice"
        assert settings.last_name == "Smith"
    finally:
        cleanup_repo(repo)


def test_update_user_profile_saves_names_and_preserves_existing_settings() -> None:
    repo = make_repo()
    try:
        repo.set_cbr_update_notifications(1001, True)

        settings = repo.update_user_profile(
            telegram_id=1001,
            username="alice",
            first_name="Alice",
            last_name="Smith",
        )

        assert settings.username == "alice"
        assert settings.first_name == "Alice"
        assert settings.last_name == "Smith"
        assert settings.cbr_update_notifications is True
    finally:
        cleanup_repo(repo)


def test_update_user_profile_allows_missing_username() -> None:
    repo = make_repo()
    try:
        settings = repo.update_user_profile(
            telegram_id=1001,
            username=None,
            first_name="Alice",
            last_name=None,
        )

        assert settings.username is None
        assert settings.first_name == "Alice"
        assert settings.last_name is None
    finally:
        cleanup_repo(repo)


def test_list_admin_users_returns_latest_30_users() -> None:
    repo = make_repo()
    try:
        for telegram_id in range(1000, 1035):
            repo.update_user_profile(
                telegram_id=telegram_id,
                username=f"user{telegram_id}",
                first_name=f"User {telegram_id}",
                last_name=None,
            )

        users = repo.list_admin_users(limit=30)

        assert len(users) == 30
    finally:
        cleanup_repo(repo)


@pytest.mark.asyncio
async def test_start_handler_updates_user_profile() -> None:
    repo = make_repo()
    message = FakeMessage(username="alice", first_name="Alice", last_name="Smith")
    try:
        await start_handler(message, repo=repo)

        settings = repo.get_user_settings(1001)

        assert settings.username == "alice"
        assert settings.first_name == "Alice"
        assert settings.last_name == "Smith"
        assert message.answers
    finally:
        cleanup_repo(repo)


@pytest.mark.asyncio
async def test_user_profile_middleware_updates_profile_for_any_message() -> None:
    repo = make_repo()
    middleware = UserProfileMiddleware()
    message = FakeMessage(username="alice_old", first_name="Alice", last_name="Old")
    repo.update_user_profile(1001, "alice_old", "Alice", "Old")
    message.from_user.username = "alice_new"
    message.from_user.last_name = "New"

    async def handler(event, data):
        return "handled"

    try:
        result = await middleware(handler, message, {"repo": repo})
        settings = repo.get_user_settings(1001)

        assert result == "handled"
        assert settings.username == "alice_new"
        assert settings.first_name == "Alice"
        assert settings.last_name == "New"
    finally:
        cleanup_repo(repo)


@pytest.mark.asyncio
async def test_user_profile_middleware_updates_profile_for_callback() -> None:
    repo = make_repo()
    middleware = UserProfileMiddleware()
    callback = SimpleNamespace(
        from_user=SimpleNamespace(
            id=1001,
            username=None,
            first_name="Alice",
            last_name="Callback",
        )
    )

    async def handler(event, data):
        return "handled"

    try:
        result = await middleware(handler, callback, {"repo": repo})
        settings = repo.get_user_settings(1001)

        assert result == "handled"
        assert settings.username is None
        assert settings.first_name == "Alice"
        assert settings.last_name == "Callback"
    finally:
        cleanup_repo(repo)
