import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings
from services.cbr import CBRService, CBRServiceError
from services.converter import (
    SUPPORTED_CALCULATOR_CURRENCIES,
    convert_currency as calculate_conversion,
    format_calculator_result,
    is_supported_request,
    looks_like_convert_attempt,
    parse_convert_request,
)
from services.formatter import DEFAULT_CURRENCIES, format_rates

logger = logging.getLogger(__name__)
router = Router(name="converter")

UNKNOWN_CURRENCY_TEXT = (
    "Неизвестная валюта. Сейчас доступны: "
    + ", ".join(SUPPORTED_CALCULATOR_CURRENCIES)
    + "."
)
CONVERT_HINT_TEXT = (
    "Введите сумму и валюту, например:\n\n"
    "100 usd\n"
    "10 000 eur\n"
    "10 000 usd +2%\n"
    "1 000 000 rub usd"
)


def calculator_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Курсы сейчас", callback_data="calc:rates")],
            [
                InlineKeyboardButton(text="⚙️ Источник: ЦБ РФ", callback_data="calc:source"),
                InlineKeyboardButton(text="🔁 Новый расчёт", callback_data="calc:new"),
            ],
        ]
    )


@router.callback_query(F.data == "calc:source")
async def show_rate_source(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Источник курса: официальный курс ЦБ РФ.")


@router.callback_query(F.data == "calc:new")
async def new_calculation(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(CONVERT_HINT_TEXT)


@router.callback_query(F.data == "calc:rates")
async def show_current_rates_from_calculator(
    callback: CallbackQuery,
    cbr_service: CBRService,
    app_config: Settings,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    today = datetime.now(ZoneInfo(app_config.timezone)).date()
    try:
        snapshot = await cbr_service.get_rates_with_delta(today)
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates from calculator button")
        await callback.message.answer("Не удалось получить курсы ЦБ РФ. Попробуйте чуть позже.")
        return

    await callback.message.answer(format_rates(snapshot, DEFAULT_CURRENCIES))


@router.message(F.text)
async def convert_currency(
    message: Message,
    cbr_service: CBRService,
    app_config: Settings,
) -> None:
    if message.text is None:
        return

    request = parse_convert_request(message.text)
    if request is None:
        if looks_like_convert_attempt(message.text):
            await message.answer(CONVERT_HINT_TEXT)
        return

    if not is_supported_request(request):
        await message.answer(UNKNOWN_CURRENCY_TEXT)
        return

    today = datetime.now(ZoneInfo(app_config.timezone)).date()
    try:
        snapshot = await cbr_service.fetch_rates(today)
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates for converter")
        await message.answer("Не удалось получить текущий курс ЦБ РФ. Попробуйте чуть позже.")
        return

    result = calculate_conversion(request, snapshot)
    if result is None:
        await message.answer("Курс выбранной валюты сейчас недоступен. Попробуйте чуть позже.")
        return

    await message.answer(
        format_calculator_result(result),
        reply_markup=calculator_result_keyboard(),
    )
