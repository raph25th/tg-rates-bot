import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

logger = logging.getLogger(__name__)
router = Router()

CBR_RATES_BUTTON = "📊 Курс ЦБ РФ"
INVESTING_RATES_BUTTON = "📈 Курс Investing"
CBR_CALC_BUTTON = "🧮 Расчёт по ЦБ РФ"
INVESTING_CALC_BUTTON = "💱 Расчёт по Investing"
CAPABILITIES_BUTTON = "❓ Что умеет бот"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CBR_RATES_BUTTON), KeyboardButton(text=INVESTING_RATES_BUTTON)],
            [KeyboardButton(text=CBR_CALC_BUTTON), KeyboardButton(text=INVESTING_CALC_BUTTON)],
            [KeyboardButton(text=CAPABILITIES_BUTTON)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else "unknown"
    logger.info("Received /start from %s", user_id)
    await message.answer(
        "Бот работает 🚀\n\n"
        "Выберите действие в меню или просто напишите сумму и валюту:\n"
        "100 usd",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text == CBR_CALC_BUTTON)
async def cbr_converter_hint(message: Message) -> None:
    await message.answer(
        "🧮 Расчёт по ЦБ РФ\n\n"
        "Напишите сумму и валюту:\n\n"
        "100 usd\n"
        "10 000 eur +2%\n"
        "1 000 000 rub в usd"
    )
