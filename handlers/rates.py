import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, Filter
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings
from db.repo import UserRepository
from handlers.start import CBR_RATES_BUTTON, INVESTING_RATES_BUTTON, main_menu_keyboard
from services.cbr import CBRService, CBRServiceError
from services.cbr_date_parser import parse_cbr_date
from services.formatter import DEFAULT_CURRENCIES, format_rates
from services.rates.cbr import rates_from_snapshot
from services.rates.formatter import DEFAULT_RATE_ORDER, format_cbr_rates
from services.rates.market import MARKET_RATE_ORDER, MarketRateProviderError
from services.rates.market.formatter import format_market_rates

logger = logging.getLogger(__name__)
router = Router(name="rates")

CBR_DATE_STATE = "awaiting_cbr_date"
user_state: dict[int, str] = {}


class AwaitingCbrDate(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and user_state.get(message.from_user.id) == CBR_DATE_STATE


def cbr_rates_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Сегодня", callback_data="cbr:today")],
            [InlineKeyboardButton(text="🗓 Выбрать дату", callback_data="cbr:choose_date")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def cbr_after_rates_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🗓 Выбрать другую дату", callback_data="cbr:choose_date")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def _cbr_menu_text() -> str:
    return "📊 Курсы ЦБ РФ\n\nВыберите действие:"


def _date_prompt_text() -> str:
    return (
        "Введите дату курса в формате:\n"
        "23.04.2026\n\n"
        "Можно также написать:\n"
        "23 апреля"
    )


def _date_error_text() -> str:
    return (
        "Не понял дату.\n\n"
        "Введите дату в формате:\n"
        "23.04.2026\n\n"
        "или:\n"
        "23 апреля"
    )


async def _fetch_rates_for_requested_date(
    cbr_service: CBRService,
    requested_date: date,
    fetched_at: datetime,
) -> tuple[str, str | None]:
    snapshot = await cbr_service.fetch_rates(requested_date)
    if snapshot.date > requested_date or (requested_date - snapshot.date).days > 7:
        raise CBRServiceError(f"Could not find available CBR rates near {requested_date.isoformat()}")

    rates = rates_from_snapshot(snapshot, fetched_at=fetched_at, source="CBR")
    warning = None
    if snapshot.date != requested_date:
        warning = (
            f"На {requested_date.strftime('%d.%m.%Y')} курс ЦБ РФ не опубликован.\n"
            f"Показан ближайший доступный курс на {snapshot.date.strftime('%d.%m.%Y')}."
        )

    return format_cbr_rates(rates, DEFAULT_RATE_ORDER), warning


async def _answer_cbr_rates(
    message: Message,
    cbr_service: CBRService,
    app_config: Settings,
    requested_date: date,
    *,
    warn_on_fallback: bool = True,
) -> None:
    timezone = ZoneInfo(app_config.timezone)
    fetched_at = datetime.now(timezone)
    try:
        text, warning = await _fetch_rates_for_requested_date(cbr_service, requested_date, fetched_at)
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates for %s", requested_date.isoformat())
        await message.answer("Не удалось получить курсы ЦБ РФ. Попробуйте чуть позже.")
        return

    if warning and warn_on_fallback:
        text = f"{warning}\n\n{text}"

    await message.answer(text, reply_markup=cbr_after_rates_keyboard())


@router.message(F.text == CBR_RATES_BUTTON)
async def show_cbr_rates_button(message: Message) -> None:
    await message.answer(_cbr_menu_text(), reply_markup=cbr_rates_menu_keyboard())


@router.callback_query(F.data == "cbr:today")
async def show_cbr_rates_today(
    callback: CallbackQuery,
    cbr_service: CBRService,
    app_config: Settings,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    today = datetime.now(ZoneInfo(app_config.timezone)).date()
    await _answer_cbr_rates(callback.message, cbr_service, app_config, today, warn_on_fallback=False)


@router.callback_query(F.data == "cbr:choose_date")
async def choose_cbr_date(callback: CallbackQuery) -> None:
    await callback.answer()
    user_state[callback.from_user.id] = CBR_DATE_STATE
    if isinstance(callback.message, Message):
        await callback.message.answer(_date_prompt_text())


@router.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Главное меню", reply_markup=main_menu_keyboard())


@router.message(AwaitingCbrDate())
async def handle_cbr_date_input(
    message: Message,
    cbr_service: CBRService,
    app_config: Settings,
) -> None:
    if message.from_user is None or message.text is None:
        return

    parsed_date = parse_cbr_date(
        message.text,
        today=datetime.now(ZoneInfo(app_config.timezone)).date(),
    )
    if parsed_date is None:
        await message.answer(_date_error_text())
        return

    user_state.pop(message.from_user.id, None)
    await _answer_cbr_rates(message, cbr_service, app_config, parsed_date)


@router.message(F.text == INVESTING_RATES_BUTTON)
async def show_investing_rates_button(message: Message, market_rate_provider) -> None:
    try:
        rates = await market_rate_provider.get_rates(list(MARKET_RATE_ORDER))
    except MarketRateProviderError as exc:
        await message.answer(str(exc))
        return

    await message.answer(format_market_rates(rates, MARKET_RATE_ORDER))


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
