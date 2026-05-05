from datetime import date
from pathlib import Path
from uuid import uuid4

from db.repo import UserRepository
from handlers.notifications import cbr_notifications_keyboard, cbr_notifications_text


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


def test_cbr_notifications_screen_is_short_and_has_actions() -> None:
    assert cbr_notifications_text() == (
        "🔔 Уведомления ЦБ\n"
        "\n"
        "Я пришлю курс ЦБ РФ после его обновления.\n"
        "\n"
        "Выберите режим:"
    )

    keyboard = cbr_notifications_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("✅ Получать после обновления", "cbr_notify:on"),
        ("❌ Не получать", "cbr_notify:off"),
        ("🏠 Главное меню", "main_menu"),
    ]


def test_user_can_enable_and_disable_cbr_update_notifications() -> None:
    repo = make_repo()
    try:
        enabled = repo.set_cbr_update_notifications(1001, True)
        assert enabled.cbr_update_notifications is True
        assert repo.get_cbr_update_notification_users()[0].telegram_id == 1001

        disabled = repo.set_cbr_update_notifications(1001, False)
        assert disabled.cbr_update_notifications is False
        assert repo.get_cbr_update_notification_users() == []
    finally:
        cleanup_repo(repo)


def test_last_sent_cbr_date_is_saved() -> None:
    repo = make_repo()
    try:
        repo.set_cbr_update_notifications(1001, True)
        repo.mark_cbr_update_notification_sent(1001, date(2026, 5, 6))

        settings = repo.get_user_settings(1001)

        assert settings.last_sent_cbr_date == date(2026, 5, 6)
        assert repo.get_cbr_update_notification_users()[0].last_sent_cbr_date == date(2026, 5, 6)
    finally:
        cleanup_repo(repo)
