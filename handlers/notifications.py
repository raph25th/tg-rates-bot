from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from db.repo import UserRepository
from handlers.start import CBR_NOTIFICATIONS_BUTTON, main_menu_keyboard

router = Router(name="notifications")


def cbr_notifications_text() -> str:
    return (
        "🔔 Уведомления ЦБ\n"
        "\n"
        "Я пришлю курс ЦБ РФ после его обновления.\n"
        "\n"
        "Выберите режим:"
    )


def cbr_notifications_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Получать после обновления", callback_data="cbr_notify:on")],
            [InlineKeyboardButton(text="❌ Не получать", callback_data="cbr_notify:off")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


@router.message(F.text == CBR_NOTIFICATIONS_BUTTON)
async def show_cbr_notifications(message: Message) -> None:
    await message.answer(cbr_notifications_text(), reply_markup=cbr_notifications_keyboard())


@router.callback_query(F.data == "cbr_notify:on")
async def enable_cbr_notifications(callback: CallbackQuery, repo: UserRepository) -> None:
    await callback.answer()
    repo.set_cbr_update_notifications(callback.from_user.id, True)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "✅ Уведомления включены\n"
            "\n"
            "Я пришлю курс ЦБ РФ после его обновления."
        )


@router.callback_query(F.data == "cbr_notify:off")
async def disable_cbr_notifications(callback: CallbackQuery, repo: UserRepository) -> None:
    await callback.answer()
    repo.set_cbr_update_notifications(callback.from_user.id, False)
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "🔕 Уведомления отключены\n"
            "\n"
            "Вы больше не будете получать автоматическое сообщение после обновления курса ЦБ РФ."
        )


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())
