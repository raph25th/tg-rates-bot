import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

logger = logging.getLogger(__name__)
router = Router()


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Курсы сейчас")],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="💱 Конвертер"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else "unknown"
    logger.info("Received /start from %s", user_id)
    print(f"Received /start from {user_id}", flush=True)
    await message.answer("Бот работает 🚀")


@router.message(F.text == "💱 Конвертер")
async def converter_hint(message: Message) -> None:
    await message.answer("Введите сумму и валюту, например: 10000 usd или 1 000 000 rub usd")
