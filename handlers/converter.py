import logging
import re
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Settings
from core.models import CurrencyRate, RatesSnapshot
from handlers.start import (
    AGENT_CBR_CALC_BUTTON,
    AGENT_CUSTOM_CALC_BUTTON,
    AGENT_MARKET_CALC_BUTTON,
    CAPABILITIES_BUTTON,
    CBR_CALC_BUTTON,
    CUSTOM_CALC_BUTTON,
    INVESTING_CALC_BUTTON,
    main_menu_keyboard,
)
from services.cbr import CBRService, CBRServiceError
from services.converter import (
    AgentCalculationResult,
    SUPPORTED_CALCULATOR_CURRENCIES,
    convert_agent_calculation,
    convert_currency as calculate_conversion,
    format_agent_calculation_result,
    format_agent_assignment_rate,
    format_client_calculation_text,
    format_custom_agent_calculation_result,
    format_custom_calculation_result,
    is_supported_request,
    looks_like_convert_attempt,
    parse_convert_request,
)
from core.money import format_number
from services.ruble_words import amount_to_russian_words
from services.rates.market import MarketRate, MarketRateProviderError, PairUnavailableError

logger = logging.getLogger(__name__)
router = Router(name="converter")

CBR_SOURCE = "CBR"
MARKET_SOURCE = "MARKET"
INVESTING_SOURCE = MARKET_SOURCE
AGENT_CBR_SOURCE = "AGENT_CBR"
AGENT_MARKET_SOURCE = "AGENT_MARKET"
CUSTOM_SOURCE = "CUSTOM"
AGENT_CUSTOM_SOURCE = "AGENT_CUSTOM"
user_rate_source: dict[int, str] = {}
last_agent_calculations: dict[int, AgentCalculationResult] = {}
_CUSTOM_RATE_RE = re.compile(r"^\s*(?P<rate>\d+(?:[.,]\d+)?)\s+(?P<request>.+?)\s*$")

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
EXTRA_PAYMENT_REVERSE_UNSUPPORTED_TEXT = "Доп. платёж пока поддерживается только для расчётов из валюты в RUB."
AGENT_REVERSE_UNSUPPORTED_TEXT = "Агентский расчёт пока поддерживается только для расчётов из валюты в RUB."
AGENT_PERCENT_REQUIRED_TEXT = "Для агентского расчёта укажите ставку клиента, например: 10 000 USD +2,5%"
AGENT_RATE_TOO_LOW_TEXT = "Агентская ставка должна быть больше 0,1%."
NO_AGENT_CALCULATION_TEXT = (
    "Сначала выполните агентский расчёт, например:\n"
    "\n"
    "10 000 USD +2,5%\n"
    "50 200 CNY +2,5% +200ПП"
)
AGENT_HINT_TEXT = (
    "Введите сумму, ставку и при необходимости доп. платёж.\n"
    "\n"
    "Примеры:\n"
    "10 000 USD +2,5%\n"
    "10 000 USD +2,5% +100ПП\n"
    "50 200 CNY +2,5% +200ПП"
)
CUSTOM_CALC_HINT_TEXT = (
    "🧮 Расчёт по своему курсу\n"
    "\n"
    "Введите курс, сумму и валюту.\n"
    "\n"
    "Формат:\n"
    "76,50 10 000 USD\n"
    "\n"
    "Примеры:\n"
    "76,50 10 000 USD\n"
    "76.50 10 000 USD\n"
    "12,80 50 200 CNY\n"
    "21,30 100 000 AED"
)
CUSTOM_CALC_PARSE_ERROR_TEXT = (
    "Не удалось разобрать расчёт.\n"
    "\n"
    "Используйте формат:\n"
    "76,50 10 000 USD\n"
    "\n"
    "Где:\n"
    "76,50 — собственный курс\n"
    "10 000 USD — сумма инвойса"
)
AGENT_CUSTOM_CALC_HINT_TEXT = (
    "🤝 Агентский расчёт по своему курсу\n"
    "\n"
    "Введите курс, сумму, валюту и ставку.\n"
    "\n"
    "Формат:\n"
    "76,50 10 000 USD +2,5% +100ПП\n"
    "\n"
    "Примеры:\n"
    "76,50 10 000 USD +2,5%\n"
    "76.50 10 000 USD +2,5% +100ПП"
)
AGENT_CUSTOM_CALC_PARSE_ERROR_TEXT = (
    "Не удалось разобрать агентский расчёт.\n"
    "\n"
    "Используйте формат:\n"
    "76,50 10 000 USD +2,5% +100ПП\n"
    "\n"
    "Где:\n"
    "76,50 — собственный курс\n"
    "10 000 USD — сумма инвойса\n"
    "+2,5% — ставка клиенту\n"
    "+100ПП — доп. платёж, если нужен"
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


def market_rates_to_snapshot(rates: dict[str, MarketRate]) -> RatesSnapshot:
    first_rate = next(iter(rates.values()))
    rate_date = first_rate.fetched_at.date()
    return RatesSnapshot(
        date=rate_date,
        rates={
            rate.code: CurrencyRate(
                code=rate.code,
                name=rate.pair,
                nominal=1,
                value=rate.value,
                unit_rate=rate.value,
                date=rate.fetched_at.date(),
            )
            for rate in rates.values()
        },
    )


def get_capabilities_hint() -> str:
    return (
        "❓ Что умеет бот\n"
        "\n"
        "Бот помогает быстро считать валюту по официальному курсу ЦБ РФ и рыночному ориентиру.\n"
        "\n"
        "📊 Курс ЦБ РФ\n"
        "Официальный курс Банка России. Обновляется один раз в день.\n"
        "\n"
        "📈 Рыночный курс\n"
        "Ориентировочный курс в моменте по данным Yahoo Finance. Может немного отличаться от банков, обменников и торговых платформ.\n"
        "\n"
        "🧮 Расчёт по ЦБ РФ\n"
        "Подходит для расчётов по официальному курсу.\n"
        "\n"
        "💱 Расчёт по рынку\n"
        "Подходит для предварительных расчётов в течение дня.\n"
        "\n"
        "📉 Спред\n"
        "Бот показывает разницу между курсом ЦБ РФ и рыночным курсом для USD, AED, CNY и EUR.\n"
        "\n"
        "🔔 Уведомления ЦБ\n"
        "Бот присылает курс ЦБ РФ после обновления и показывает, насколько курс вырос или снизился относительно предыдущего опубликованного курса.\n"
        "\n"
        "Примеры:\n"
        "\n"
        "Валюта → рубли:\n"
        "100 usd\n"
        "10 000 eur\n"
        "10 000 aed +2%\n"
        "\n"
        "Рубли → валюта:\n"
        "1 000 000 rub в usd\n"
        "500 000 рублей в eur\n"
        "5 000 000 ₽ в cny\n"
        "\n"
        "С процентом к курсу:\n"
        "10 000 usd +2%\n"
        "10 000 usd в руб -1,5%\n"
        "1 000 000 rub в usd +2%\n"
        "\n"
        "С доп. платежом:\n"
        "10 000 USD +2% +100ПП\n"
        "50 200 CNY +2% +200ПП\n"
        "\n"
        "Доп. платёж всегда считается в USD по тому же источнику курса и с той же ставкой.\n"
        "\n"
        "Агентский расчёт:\n"
        "10 000 USD +2,5%\n"
        "10 000 USD +2,5% +100ПП\n"
        "50 200 CNY +2,5% +200ПП\n"
        "\n"
        "В агентском расчёте ставка клиента делится на основную ставку и агентское вознаграждение 0,1%.\n"
        "Доп. платёж всегда считается в USD и входит в основной платёж.\n"
        "\n"
        "Можно писать как код валюты, так и словами:\n"
        "10 000 usd\n"
        "10 000 долларов\n"
        "1 000 000 рублей в евро\n"
        "\n"
        "Доступные валюты:\n"
        "USD, EUR, CNY, GBP, AED, THB, KRW, JPY"
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
        "10 000 usd +2% +100ПП\n"
        "50 200 CNY +2% +200ПП\n"
        "10 000 USD +2,5%\n"
        "50 200 CNY +2,5% +200ПП\n"
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


def agent_calculation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Версия для поручения", callback_data="agent:assignment_text")],
            [
                InlineKeyboardButton(text="🔁 Новый расчёт", callback_data="calc:new"),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"),
            ],
        ]
    )


def _save_last_agent_calculation(message: Message, result: AgentCalculationResult) -> None:
    if message.from_user is not None:
        last_agent_calculations[message.from_user.id] = result


def _format_rub_number(value) -> str:
    return f"{format_number(value, places=2, trim_zero_fraction=False)} RUB"


def format_agent_assignment_text(result: AgentCalculationResult) -> str:
    return "\n".join(
        [
            "Версия для поручения:",
            "",
            "Курс в поручении:",
            format_agent_assignment_rate(result),
            "",
            "Основной платёж:",
            _format_rub_number(result.main_payment_rub),
            amount_to_russian_words(result.main_payment_rub),
            "",
            "Агентское вознаграждение:",
            _format_rub_number(result.agent_fee_rub),
            amount_to_russian_words(result.agent_fee_rub),
            "",
            "Итоговая сумма:",
            _format_rub_number(result.final_result),
            amount_to_russian_words(result.final_result),
        ]
    )


def get_agent_assignment_text_for_user(user_id: int) -> str:
    result = last_agent_calculations.get(user_id)
    if result is None:
        return NO_AGENT_CALCULATION_TEXT
    return format_agent_assignment_text(result)


def _set_user_source(message: Message, source: str) -> None:
    if message.from_user is not None:
        user_rate_source[message.from_user.id] = source


def _get_user_source(message: Message) -> str:
    if message.from_user is None:
        return CBR_SOURCE
    return user_rate_source.get(message.from_user.id, CBR_SOURCE)


def _is_agent_source(source: str) -> bool:
    return source in {AGENT_CBR_SOURCE, AGENT_MARKET_SOURCE, AGENT_CUSTOM_SOURCE}


def _agent_uses_market(source: str) -> bool:
    return source == AGENT_MARKET_SOURCE or source == MARKET_SOURCE


def _parse_custom_rate_request(text: str):
    match = _CUSTOM_RATE_RE.match(text)
    if match is None:
        return None

    try:
        custom_rate = Decimal(match.group("rate").replace(",", "."))
    except InvalidOperation:
        return None
    if custom_rate <= 0:
        return None

    request = parse_convert_request(match.group("request"))
    if request is None:
        return None
    return custom_rate, request


def _custom_rate_date(app_config: Settings):
    return datetime.now(ZoneInfo(app_config.timezone)).date()


def _custom_rate_snapshot(custom_rate: Decimal, code: str, app_config: Settings) -> RatesSnapshot:
    rate_date = _custom_rate_date(app_config)
    rate = CurrencyRate(
        code=code,
        name="Собственный курс",
        nominal=1,
        value=custom_rate,
        unit_rate=custom_rate,
        date=rate_date,
    )
    return RatesSnapshot(date=rate_date, rates={code: rate})


def _make_agent_request(request):
    client_percent = request.percent
    return replace(
        request,
        is_agent_calculation=True,
        client_percent=client_percent,
        main_rate_percent=client_percent - request.agent_fee_percent if client_percent is not None else None,
        extra_payment_usd=request.extra_payment_amount,
    )


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


@router.message(F.text == CUSTOM_CALC_BUTTON)
async def choose_custom_calculation(message: Message) -> None:
    _set_user_source(message, CUSTOM_SOURCE)
    await message.answer(CUSTOM_CALC_HINT_TEXT)


@router.callback_query(F.data == "calc:cbr")
async def choose_cbr_calculation_from_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        if callback.from_user is not None:
            user_rate_source[callback.from_user.id] = CBR_SOURCE
        await callback.message.answer(
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


@router.message(F.text == AGENT_CBR_CALC_BUTTON)
async def choose_agent_cbr_calculation(message: Message) -> None:
    _set_user_source(message, AGENT_CBR_SOURCE)
    await message.answer(
        "🤝 Агентский расчёт по ЦБ РФ\n\n"
        f"{AGENT_HINT_TEXT}"
    )


@router.message(F.text == AGENT_MARKET_CALC_BUTTON)
async def choose_agent_market_calculation(message: Message, market_rate_provider) -> None:
    try:
        await market_rate_provider.get_rate("USD")
    except MarketRateProviderError as exc:
        await message.answer(str(exc))
        return

    _set_user_source(message, AGENT_MARKET_SOURCE)
    await message.answer(
        "🤝 Агентский расчёт по рынку\n\n"
        f"{AGENT_HINT_TEXT}"
    )


@router.message(F.text == AGENT_CUSTOM_CALC_BUTTON)
async def choose_agent_custom_calculation(message: Message) -> None:
    _set_user_source(message, AGENT_CUSTOM_SOURCE)
    await message.answer(AGENT_CUSTOM_CALC_HINT_TEXT)


@router.callback_query(F.data == "calc:new")
async def new_calculation(callback: CallbackQuery) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(get_new_calculation_hint())


@router.callback_query(F.data == "agent:assignment_text")
async def show_agent_assignment_text(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(get_agent_assignment_text_for_user(callback.from_user.id))


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

    active_source = _get_user_source(message)
    if active_source in {CUSTOM_SOURCE, AGENT_CUSTOM_SOURCE}:
        parsed_custom = _parse_custom_rate_request(message.text)
        if parsed_custom is None:
            await message.answer(
                AGENT_CUSTOM_CALC_PARSE_ERROR_TEXT
                if active_source == AGENT_CUSTOM_SOURCE
                else CUSTOM_CALC_PARSE_ERROR_TEXT
            )
            return

        custom_rate, request = parsed_custom
        if not is_supported_request(request) or request.is_reverse:
            await message.answer(
                AGENT_CUSTOM_CALC_PARSE_ERROR_TEXT
                if active_source == AGENT_CUSTOM_SOURCE
                else CUSTOM_CALC_PARSE_ERROR_TEXT
            )
            return

        snapshot = _custom_rate_snapshot(custom_rate, request.from_code, app_config)
        if active_source == CUSTOM_SOURCE:
            if request.percent is not None or request.extra_payment_amount is not None or request.is_agent_calculation:
                await message.answer(CUSTOM_CALC_PARSE_ERROR_TEXT)
                return

            result = calculate_conversion(request, snapshot, source=CUSTOM_SOURCE)
            if result is None:
                await message.answer(CUSTOM_CALC_PARSE_ERROR_TEXT)
                return

            await message.answer(
                format_custom_calculation_result(result),
                reply_markup=calculator_result_keyboard(),
            )
            return

        request = _make_agent_request(request)
        if request.percent is None:
            await message.answer(AGENT_CUSTOM_CALC_PARSE_ERROR_TEXT)
            return
        if request.percent <= request.agent_fee_percent:
            await message.answer(AGENT_RATE_TOO_LOW_TEXT)
            return

        result = convert_agent_calculation(request, snapshot, source=AGENT_CUSTOM_SOURCE)
        if result is None:
            await message.answer(AGENT_CUSTOM_CALC_PARSE_ERROR_TEXT)
            return

        _save_last_agent_calculation(message, result)
        await message.answer(
            format_custom_agent_calculation_result(result),
            reply_markup=agent_calculation_keyboard(),
        )
        return

    request = parse_convert_request(message.text)
    if request is None:
        if looks_like_convert_attempt(message.text):
            await message.answer(get_new_calculation_hint())
        return

    if not is_supported_request(request):
        await message.answer(UNKNOWN_CURRENCY_TEXT)
        return

    is_agent_calculation = request.is_agent_calculation or _is_agent_source(active_source)
    if is_agent_calculation:
        request = _make_agent_request(request)
        if request.is_reverse:
            await message.answer(AGENT_REVERSE_UNSUPPORTED_TEXT)
            return
        if request.percent is None:
            await message.answer(AGENT_PERCENT_REQUIRED_TEXT)
            return
        if request.percent <= request.agent_fee_percent:
            await message.answer(AGENT_RATE_TOO_LOW_TEXT)
            return

        if _agent_uses_market(active_source):
            rate_code = request.from_code
            try:
                rate_codes = [rate_code]
                market_rates = await market_rate_provider.get_rates(rate_codes)
                snapshot = market_rates_to_snapshot(market_rates)
            except PairUnavailableError as exc:
                await message.answer(str(exc))
                return
            except MarketRateProviderError as exc:
                user_rate_source.pop(message.from_user.id, None) if message.from_user is not None else None
                await message.answer(str(exc))
                return
            source = MARKET_SOURCE
        else:
            try:
                snapshot = await cbr_service.get_latest_cbr_rates()
                logger.info("CBR latest loaded: cbr_date=%s", snapshot.date.isoformat())
                logger.info("CBR calculation uses latest cbr_date=%s", snapshot.date.isoformat())
            except CBRServiceError:
                logger.exception("Could not fetch CBR rates for agent converter")
                await message.answer("Не удалось получить текущий курс ЦБ РФ. Попробуйте чуть позже.")
                return
            source = "ЦБ РФ — официальный курс"

        result = convert_agent_calculation(request, snapshot, source=source)
        if result is None:
            await message.answer("Курс выбранной валюты сейчас недоступен. Попробуйте чуть позже.")
            return

        _save_last_agent_calculation(message, result)
        await message.answer(
            format_agent_calculation_result(result),
            reply_markup=agent_calculation_keyboard(),
        )
        return

    if request.is_reverse and request.extra_payment_amount is not None:
        await message.answer(EXTRA_PAYMENT_REVERSE_UNSUPPORTED_TEXT)
        return

    if active_source == MARKET_SOURCE:
        rate_code = request.to_code if request.direction == "rub_to_currency" else request.from_code
        try:
            if request.extra_payment_amount is not None:
                rate_codes = list(dict.fromkeys([rate_code, "USD"]))
                market_rates = await market_rate_provider.get_rates(rate_codes)
                market_snapshot = market_rates_to_snapshot(market_rates)
            else:
                market_rate = await market_rate_provider.get_rate(rate_code)
                market_snapshot = market_rate_to_snapshot(market_rate)
        except PairUnavailableError as exc:
            await message.answer(str(exc))
            return
        except MarketRateProviderError as exc:
            user_rate_source.pop(message.from_user.id, None) if message.from_user is not None else None
            await message.answer(str(exc))
            return

        result = calculate_conversion(request, market_snapshot, source=MARKET_SOURCE)
        if result is None:
            await message.answer(f"Пара {rate_code}/RUB временно недоступна в рыночном источнике.")
            return

        await message.answer(
            format_client_calculation_text(result),
            reply_markup=calculator_result_keyboard(),
        )
        return

    try:
        snapshot = await cbr_service.get_latest_cbr_rates()
        logger.info("CBR latest loaded: cbr_date=%s", snapshot.date.isoformat())
        logger.info("CBR calculation uses latest cbr_date=%s", snapshot.date.isoformat())
    except CBRServiceError:
        logger.exception("Could not fetch CBR rates for converter")
        await message.answer("Не удалось получить текущий курс ЦБ РФ. Попробуйте чуть позже.")
        return

    result = calculate_conversion(request, snapshot, source="ЦБ РФ — официальный курс")
    if result is None:
        await message.answer("Курс выбранной валюты сейчас недоступен. Попробуйте чуть позже.")
        return

    await message.answer(
        format_client_calculation_text(result),
        reply_markup=calculator_result_keyboard(),
    )
