from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from db.models import UserSettings
from db.repo import UserRepository
from handlers.start import main_menu_keyboard
from services.formatter import DEFAULT_CURRENCIES

router = Router(name="settings")

CURRENCY_BUTTONS: tuple[str, ...] = (
    "USD",
    "EUR",
    "CNY",
    "GBP",
    "AED",
    "JPY",
    "KRW",
    "THB",
)


def render_settings_text(settings: UserSettings) -> str:
    mode = "ежедневно" if settings.mode == "daily" else "вручную"
    currencies = (
        ", ".join(settings.currencies)
        if settings.currencies
        else f"по умолчанию ({', '.join(DEFAULT_CURRENCIES)})"
    )
    return f"Настройки\n\nРежим: {mode}\nВалюты: {currencies}\n\nВыберите валюты:"


def currency_keyboard(settings: UserSettings) -> InlineKeyboardMarkup:
    selected = set(settings.currencies)
    rows: list[list[InlineKeyboardButton]] = []

    row: list[InlineKeyboardButton] = []
    for code in CURRENCY_BUTTONS:
        row.append(
            InlineKeyboardButton(
                text=f"{'✅' if code in selected else '⬜'} {code}",
                callback_data=f"settings:currency:{code}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []

    if row:
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(text="💾 Сохранить", callback_data="settings:save"),
            InlineKeyboardButton(text="⬅️ Назад", callback_data="settings:back"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: Message, repo: UserRepository) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    settings = repo.get_user_settings(message.from_user.id)
    await message.answer(render_settings_text(settings), reply_markup=currency_keyboard(settings))


@router.callback_query(F.data.startswith("settings:"))
async def update_settings(callback: CallbackQuery, repo: UserRepository) -> None:
    if callback.from_user is None or callback.data is None:
        await callback.answer()
        return

    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    value = parts[2] if len(parts) > 2 else ""

    if action == "currency" and value in CURRENCY_BUTTONS:
        settings = repo.toggle_currency(callback.from_user.id, value)
        await callback.answer()
        await _edit_currency_markup(callback, settings)
        return

    if action == "save":
        settings = repo.get_user_settings(callback.from_user.id)
        currencies = settings.currencies or list(DEFAULT_CURRENCIES)
        await callback.answer("Сохранено")
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"✅ Валюты сохранены: {', '.join(currencies)}",
                reply_markup=main_menu_keyboard(),
            )
        return

    if action == "back":
        await callback.answer()
        if isinstance(callback.message, Message):
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
            await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())
        return

    await callback.answer()


async def _edit_currency_markup(callback: CallbackQuery, settings: UserSettings) -> None:
    if not isinstance(callback.message, Message):
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=currency_keyboard(settings))
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
