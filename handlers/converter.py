import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings
from handlers.start import CAPABILITIES_BUTTON, CBR_CALC_BUTTON, INVESTING_CALC_BUTTON
from services.cbr import CBRService, CBRServiceError
from services.converter import (
    SUPPORTED_CALCULATOR_CURRENCIES,
    convert_currency as calculate_conversion,
    format_calculator_result,
    is_supported_request,
    looks_like_convert_attempt,
    parse_convert_request,
)
from services.rates.cbr import CBRRateSource
from services.rates.formatter import DEFAULT_RATE_ORDER, format_cbr_rates

logger = logging.getLogger(__name__)
router = Router(name="converter")

CBR_SOURCE = "CBR"
INVESTING_SOURCE = "INVESTING"
user_rate_source: dict[int, str] = {}

UNKNOWN_CURRENCY_TEXT = (
    "Неизвестная валюта. Сейчас доступны: "
    + ", ".join(SUPPORTED_CALCULATOR_CURRENCIES)
    + "."
)
INVESTING_CALC_UNAVAILABLE_TEXT = (
    "⚡ Расчёт по курсу Investing\n"
    "\n"
    "Скоро здесь будет расчёт по live-курсу Investing.\n"
    "\n"
    "Пока можно использовать расчёт по курсу ЦБ РФ:\n"
    "100 usd\n"
    "10 000 usd +2%"
)


def get_capabilities_hint() -> str:
    return (
        "💱 Что умеет бот\n"
        "\n"
        "Я умею считать валюту по курсу ЦБ РФ, а также готовлю поддержку live-курсов Investing.\n"
        "\n"
        "Примеры:\n"
        "\n"
        "Валюта → рубли:\n"
        "• 100 usd\n"
        "• 10 000 eur\n"
        "• 10 000 aed +2%\n"
        "\n"
        "Рубли → валюта:\n"
        "• 1 000 000 rub в usd\n"
        "• 500 000 рублей в eur\n"
        "• 5 000 000 ₽ в cny\n"
        "\n"
        "С процентом к курсу:\n"
        "• 10 000 usd +2%\n"
        "• 10 000 usd в руб -1,5%\n"
        "• 1 000 000 rub в usd +2%\n"
        "\n"
        "Доступные валюты:\n"
        "USD, EUR, CNY, GBP, AED, THB, KRW, JPY\n"
        "\n"
        "Можно писать естественно, например:\n"
        "“56 548 468 рублей в USD”"
    )


def get_new_calculation_hint() -> str:
    return (
        "💱 Новый расчёт\n"
        "\n"
        "Напишите сумму и валюту, например:\n"
        "\n"
        "100 usd\n"
        "10 000 usd +2%\n"
        "1 000 000 rub в usd\n"
        "\n"
        "Полный список возможностей — в разделе:\n"
        "❓ Что умеет бот"
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


def _set_user_source(message: Message, source: str) -> None:
    if message.from_user is not None:
        user_rate_source[message.from_user.id] = source


def _get_user_source(message: Message) -> str:
    if message.from_user is None:
        return CBR_SOURCE
    return user_rate_source.get(message.from_user.id, CBR_SOURCE)


@router.message(F.text == CAPABILITIES_BUTTON)
async def show_capabilities(message: Message) -> None:
    await message.answer(get_capabilities_hint())


@router.message(F.text == CBR_CALC_BUTTON)
async def choose_cbr_calculation(message: Message) -> None:
    _set_user_source(message, CBR_SOURCE)
    await message.answer(
        "🧮 Расчёт по курсу ЦБ РФ\n\n"
        "Напишите сумму и валюту:\n\n"
        "100 usd\n"
        "10 000 eur +2%\n"
        "1 000 000 rub в usd"
    )


@router.message(F.text == INVESTING_CALC_BUTTON)
async def choose_investing_calculation(message: Message) -> None:
    await message.answer(INVESTING_CALC_UNAVAILABLE_TEXT)


@router.callback_query(F.data == "calc:source")
async def show_rate_source(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Источник курса: официальный курс ЦБ РФ.")


@router.callback_query(F.data == "calc:new")
async def new_calculation(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(get_new_calculation_hint())


@router.callback_query(F.data == "calc:rates")
async def show_current_rates_from_calculator(
    callback: CallbackQuery,
    cbr_service: CBRService,
    app_config: Settings,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    try:
        rates = await CBRRateSource(cbr_service, app_config).get_rates()
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates from calculator button")
        await callback.message.answer("Не удалось получить курсы ЦБ РФ. Попробуйте чуть позже.")
        return

    await callback.message.answer(format_cbr_rates(rates, DEFAULT_RATE_ORDER))


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
            await message.answer(get_new_calculation_hint())
        return

    if not is_supported_request(request):
        await message.answer(UNKNOWN_CURRENCY_TEXT)
        return

    if _get_user_source(message) == INVESTING_SOURCE:
        await message.answer(INVESTING_CALC_UNAVAILABLE_TEXT)
        return

    today = datetime.now(ZoneInfo(app_config.timezone)).date()
    try:
        snapshot = await cbr_service.fetch_rates(today)
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates for converter")
        await message.answer("Не удалось получить текущий курс ЦБ РФ. Попробуйте чуть позже.")
        return

    result = calculate_conversion(request, snapshot, source="ЦБ РФ")
    if result is None:
        await message.answer("Курс выбранной валюты сейчас недоступен. Попробуйте чуть позже.")
        return

    await message.answer(
        format_calculator_result(result),
        reply_markup=calculator_result_keyboard(),
    )
