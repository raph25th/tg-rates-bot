import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings
from core.models import CurrencyRate, RatesSnapshot
from handlers.start import CAPABILITIES_BUTTON, CBR_CALC_BUTTON, INVESTING_CALC_BUTTON, main_menu_keyboard
from services.cbr import CBRService, CBRServiceError
from services.converter import (
    SUPPORTED_CALCULATOR_CURRENCIES,
    convert_currency as calculate_conversion,
    format_calculator_result,
    is_supported_request,
    looks_like_convert_attempt,
    parse_convert_request,
)
from services.rates.market import MarketRate, MarketRateProviderError, PairUnavailableError

logger = logging.getLogger(__name__)
router = Router(name="converter")

CBR_SOURCE = "CBR"
MARKET_SOURCE = "MARKET"
INVESTING_SOURCE = MARKET_SOURCE
user_rate_source: dict[int, str] = {}

UNKNOWN_CURRENCY_TEXT = (
    "Неизвестная валюта. Сейчас доступны: "
    + ", ".join(SUPPORTED_CALCULATOR_CURRENCIES)
    + "."
)
INVESTING_CALC_UNAVAILABLE_TEXT = (
    "💱 Расчёт по рынку\n"
    "\n"
    "Рыночные курсы временно недоступны.\n"
    "\n"
    "Пока можно использовать расчёт по курсу ЦБ РФ:\n"
    "100 usd\n"
    "10 000 usd +2%"
)


def market_rate_to_snapshot(rate: MarketRate) -> RatesSnapshot:
    rate_date = rate.fetched_at.date()
    currency_rate = CurrencyRate(
        code=rate.code,
        name=rate.pair,
        nominal=1,
        value=rate.value,
        unit_rate=rate.value,
        date=rate_date,
    )
    return RatesSnapshot(date=rate_date, rates={rate.code: currency_rate})


def get_capabilities_hint() -> str:
    return (
        "❓ Что умеет бот\n"
        "\n"
        "Бот умеет:\n"
        "• считать по официальному курсу ЦБ РФ\n"
        "• считать по рыночному курсу, если источник подключён\n"
        "• применять процентную корректировку к курсу\n"
        "• считать валюту в рубли и рубли в валюту\n"
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
        "Больше возможностей — в разделе:\n"
        "❓ Что умеет бот"
    )


def calculator_result_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔁 Новый расчёт", callback_data="calc:new"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
            ]
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
        "🧮 Расчёт по ЦБ РФ\n\n"
        "Напишите сумму и валюту:\n\n"
        "100 usd\n"
        "10 000 eur +2%\n"
        "1 000 000 rub в usd"
    )


@router.message(F.text == INVESTING_CALC_BUTTON)
async def choose_investing_calculation(message: Message, market_rate_provider) -> None:
    try:
        await market_rate_provider.get_rate("USD")
    except MarketRateProviderError as exc:
        await message.answer(str(exc))
        return

    _set_user_source(message, INVESTING_SOURCE)
    await message.answer(
        "💱 Расчёт по рынку\n\n"
        "Напишите сумму и валюту:\n\n"
        "100 usd\n"
        "10 000 usd +2%\n"
        "1 000 000 rub в usd"
    )


@router.callback_query(F.data == "calc:new")
async def new_calculation(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(get_new_calculation_hint())


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())


@router.message(F.text)
async def convert_currency(
    message: Message,
    cbr_service: CBRService,
    app_config: Settings,
    market_rate_provider,
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

    active_source = _get_user_source(message)

    if active_source == MARKET_SOURCE:
        rate_code = request.to_code if request.direction == "rub_to_currency" else request.from_code
        try:
            market_rate = await market_rate_provider.get_rate(rate_code)
        except PairUnavailableError as exc:
            await message.answer(str(exc))
            return
        except MarketRateProviderError as exc:
            user_rate_source.pop(message.from_user.id, None) if message.from_user is not None else None
            await message.answer(str(exc))
            return

        result = calculate_conversion(request, market_rate_to_snapshot(market_rate), source=market_rate.source)
        if result is None:
            await message.answer(f"Пара {rate_code}/RUB временно недоступна в рыночном источнике.")
            return

        await message.answer(
            format_calculator_result(result),
            reply_markup=calculator_result_keyboard(),
        )
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
