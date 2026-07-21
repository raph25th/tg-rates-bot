import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from db.repo import UserRepository

logger = logging.getLogger(__name__)
router = Router()

CBR_RATES_BUTTON = "📊 Курс ЦБ РФ"
INVESTING_RATES_BUTTON = "📈 Рыночный курс"
CBR_CALC_BUTTON = "🧮 Расчёт по ЦБ РФ"
INVESTING_CALC_BUTTON = "💱 Расчёт по рынку"
CUSTOM_CALC_BUTTON = "🧮 Расчёт по своему курсу"
AGENT_CBR_CALC_BUTTON = "🤝 Агентский расчёт по ЦБ РФ"
AGENT_MARKET_CALC_BUTTON = "🤝 Агентский расчёт по рынку"
AGENT_CUSTOM_CALC_BUTTON = "🤝 Агентский расчёт по своему курсу"
MAX_INVOICE_BUTTON = "💰 Максимальная сумма инвойса"
SPREAD_BUTTON = "📉 Спред"
CBR_NOTIFICATIONS_BUTTON = "🔔 Уведомления ЦБ"
CAPABILITIES_BUTTON = "❓ Что умеет бот"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CBR_RATES_BUTTON), KeyboardButton(text=INVESTING_RATES_BUTTON)],
            [KeyboardButton(text=CBR_CALC_BUTTON), KeyboardButton(text=INVESTING_CALC_BUTTON)],
            [KeyboardButton(text=AGENT_CBR_CALC_BUTTON), KeyboardButton(text=AGENT_MARKET_CALC_BUTTON)],
            [KeyboardButton(text=CUSTOM_CALC_BUTTON), KeyboardButton(text=AGENT_CUSTOM_CALC_BUTTON)],
            [KeyboardButton(text=MAX_INVOICE_BUTTON)],
            [KeyboardButton(text=SPREAD_BUTTON), KeyboardButton(text=CBR_NOTIFICATIONS_BUTTON)],
            [KeyboardButton(text=CAPABILITIES_BUTTON)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


@router.message(Command("start"))
async def start_handler(message: Message, repo: UserRepository | None = None) -> None:
    user_id = message.from_user.id if message.from_user else "unknown"
    logger.info("Received /start from %s", user_id)
    if repo is not None and message.from_user is not None:
        repo.update_user_profile(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
    await message.answer(
        "Привет 👋\n"
        "\n"
        "Я помогу быстро посчитать валюту в рублях и обратно.\n"
        "\n"
        "Что можно делать:\n"
        "• смотреть официальный курс ЦБ РФ\n"
        "• смотреть рыночный курс в моменте\n"
        "• пересчитывать суммы в рубли\n"
        "• пересчитывать рубли в валюту\n"
        "• добавлять процент к курсу: +2%, -1,5%\n"
        "\n"
        "Примеры:\n"
        "100 usd\n"
        "10 000 eur +2%\n"
        "1 000 000 rub в usd\n"
        "56 548 468 рублей в USD\n"
        "\n"
        "Можно писать как код валюты, так и словами:\n"
        "10 000 usd\n"
        "10 000 долларов\n"
        "1 000 000 рублей в евро\n"
        "\n"
        "Выберите действие 👇",
        reply_markup=main_menu_keyboard(),
    )
