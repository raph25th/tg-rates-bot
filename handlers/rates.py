import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from config import Settings
from db.repo import UserRepository
from handlers.start import CBR_RATES_BUTTON, INVESTING_RATES_BUTTON
from services.cbr import CBRService, CBRServiceError
from services.formatter import DEFAULT_CURRENCIES, format_rates
from services.rates.cbr import CBRRateSource
from services.rates.formatter import DEFAULT_RATE_ORDER, format_cbr_rates
from services.rates.investing import get_investing_unavailable_message

logger = logging.getLogger(__name__)
router = Router(name="rates")


@router.message(F.text == CBR_RATES_BUTTON)
async def show_cbr_rates_button(
    message: Message,
    cbr_service: CBRService,
    app_config: Settings,
) -> None:
    try:
        rates = await CBRRateSource(cbr_service, app_config).get_rates()
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates")
        await message.answer("Не удалось получить курсы ЦБ РФ. Попробуйте чуть позже.")
        return

    await message.answer(format_cbr_rates(rates, DEFAULT_RATE_ORDER))


@router.message(F.text == INVESTING_RATES_BUTTON)
async def show_investing_rates_button(message: Message) -> None:
    await message.answer(get_investing_unavailable_message())


@router.message(Command("rates"))
@router.message(F.text == "📊 Курсы сейчас")
async def show_rates(
    message: Message,
    repo: UserRepository,
    cbr_service: CBRService,
    app_config: Settings,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    repo.ensure_user(message.from_user.id)
    selected_codes = repo.get_currencies(message.from_user.id) or list(DEFAULT_CURRENCIES)
    today = datetime.now(ZoneInfo(app_config.timezone)).date()

    try:
        snapshot = await cbr_service.get_rates_with_delta(today)
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates")
        await message.answer("Не удалось получить курсы ЦБ РФ. Попробуйте чуть позже.")
        return

    await message.answer(format_rates(snapshot, selected_codes))
