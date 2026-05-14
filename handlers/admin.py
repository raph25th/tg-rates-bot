from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import Settings
from db.models import AdminUserRow, BotStats
from db.repo import UserRepository

router = Router(name="admin")

ACCESS_DENIED_TEXT = "Команда недоступна."


def _is_admin(message: Message, app_config: Settings) -> bool:
    return message.from_user is not None and app_config.is_admin(message.from_user.id)


def _is_owner(message: Message, app_config: Settings) -> bool:
    return message.from_user is not None and app_config.is_owner(message.from_user.id)


def format_stats(stats: BotStats) -> str:
    return (
        "Статистика бота:\n"
        "\n"
        f"Всего пользователей: {stats.total_users}\n"
        f"С уведомлениями ЦБ: {stats.cbr_update_notifications}\n"
        "\n"
        f"Новых за 24 часа: {stats.new_24h}\n"
        f"Новых за 7 дней: {stats.new_7d}"
    )


def _format_user_name(user: AdminUserRow) -> str:
    parts = [part for part in (user.first_name, user.last_name) if part]
    return " ".join(parts) if parts else "без имени"


def format_users(users: list[AdminUserRow]) -> str:
    lines = ["Последние пользователи:"]
    if not users:
        return "\n".join([*lines, "", "Пользователей пока нет."])

    lines.append("")
    for index, user in enumerate(users, start=1):
        username = f"@{user.username}" if user.username else "без username"
        updated_at = user.updated_at.strftime("%d.%m.%Y %H:%M")
        lines.append(f"{index}. {user.telegram_id}")
        lines.append(username)
        name = _format_user_name(user)
        if name != "без имени":
            lines.append(name)
        lines.append(f"Обновлён: {updated_at}")
        if index != len(users):
            lines.append("")
    return "\n".join(lines)


def format_users_report(stats: BotStats, users: list[AdminUserRow]) -> str:
    return "\n".join(
        [
            "Пользователи бота:",
            "",
            f"Всего: {stats.total_users}",
            f"С уведомлениями ЦБ: {stats.cbr_update_notifications}",
            "",
            format_users(users),
        ]
    )


@router.message(Command("stats"))
async def show_stats(message: Message, repo: UserRepository, app_config: Settings) -> None:
    if not _is_admin(message, app_config):
        await message.answer(ACCESS_DENIED_TEXT)
        return

    await message.answer(format_stats(repo.get_bot_stats()))


@router.message(Command("users"))
async def show_users(message: Message, repo: UserRepository, app_config: Settings) -> None:
    if not _is_owner(message, app_config):
        await message.answer(ACCESS_DENIED_TEXT)
        return

    await message.answer(format_users_report(repo.get_bot_stats(), repo.list_admin_users(limit=30)))
