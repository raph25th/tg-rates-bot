from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from config import Settings, parse_daily_time
from core.money import format_rate
from db.repo import UserRepository
from services.cbr import CBRService
from services.formatter import format_rates
from services.rates.display import currency_display_name
from services.rates.formatter import DEFAULT_RATE_ORDER

logger = logging.getLogger(__name__)

DAILY_RETRY_DELAY_MINUTES = 15
DAILY_MAX_RETRIES = 24
CBR_UPDATE_CHECK_START = time(16, 30)
CBR_UPDATE_CHECK_END = time(19, 30)
PREVIOUS_CBR_LOOKUP_DAYS = 10


@dataclass(frozen=True)
class CBRRateChange:
    delta_rub: Decimal
    delta_percent: Decimal


def setup_scheduler(
    bot: Bot,
    repo: UserRepository,
    cbr_service: CBRService,
    app_config: Settings,
) -> AsyncIOScheduler:
    timezone = ZoneInfo(app_config.timezone)
    hour, minute = parse_daily_time(app_config.default_daily_time)
    scheduler = AsyncIOScheduler(timezone=timezone)
    scheduler.add_job(
        send_daily_rates,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=timezone),
        id="daily_rates",
        kwargs={
            "bot": bot,
            "repo": repo,
            "cbr_service": cbr_service,
            "scheduler": scheduler,
            "timezone_name": app_config.timezone,
        },
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        check_cbr_update_notifications,
        trigger=CronTrigger(hour="16-19", minute="*/15", timezone=timezone),
        id="cbr_update_notifications",
        kwargs={
            "bot": bot,
            "repo": repo,
            "cbr_service": cbr_service,
            "timezone_name": app_config.timezone,
        },
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=1800,
    )
    return scheduler


def cbr_update_notification_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Курс ЦБ РФ", callback_data="cbr:menu")],
            [InlineKeyboardButton(text="🧮 Расчёт по ЦБ РФ", callback_data="calc:cbr")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


async def get_previous_cbr_rates(
    cbr_service: CBRService,
    current_cbr_date: date,
    max_lookup_days: int = PREVIOUS_CBR_LOOKUP_DAYS,
):
    for offset in range(1, max_lookup_days + 1):
        candidate_date = current_cbr_date - timedelta(days=offset)
        try:
            snapshot = await cbr_service.fetch_rates(candidate_date)
        except Exception:
            logger.exception("Could not fetch previous CBR rates for %s", candidate_date.isoformat())
            continue
        if snapshot.date < current_cbr_date:
            return snapshot
    return None


def calculate_cbr_rate_change(current_rate, previous_rate) -> CBRRateChange | None:
    if previous_rate is None or previous_rate.unit_rate == 0:
        return None
    delta_rub = current_rate.unit_rate - previous_rate.unit_rate
    delta_percent = delta_rub / previous_rate.unit_rate * Decimal("100")
    return CBRRateChange(delta_rub=delta_rub, delta_percent=delta_percent)


def _format_signed_rate(value: Decimal) -> str:
    text = format_rate(value)
    return f"+{text}" if value > 0 else text


def _format_signed_percent(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"))
    text = f"{rounded:.2f}".replace(".", ",")
    return f"+{text}" if rounded > 0 else text


def _format_change_direction(change: CBRRateChange) -> str:
    if change.delta_rub > 0:
        return "Курс вырос 📈"
    if change.delta_rub < 0:
        return "Курс снизился 📉"
    return "Курс не изменился ➖"


def format_cbr_update_notification(snapshot, previous_snapshot=None) -> str:
    lines = [
        "📊 Курсы ЦБ РФ обновлены",
        "",
        "Дата курса:",
        snapshot.date.strftime("%d.%m.%Y"),
    ]
    if previous_snapshot is None:
        lines.extend(["", "Не удалось получить предыдущий курс для сравнения."])
    else:
        lines.extend(["", "Сравнение с:", previous_snapshot.date.strftime("%d.%m.%Y")])

    for code in DEFAULT_RATE_ORDER:
        rate = snapshot.rates.get(code)
        if rate is None:
            continue
        lines.extend(
            [
                "",
                f"{rate.code} — {currency_display_name(rate.code, rate.name)}",
                f"1 {rate.code} = {format_rate(rate.unit_rate)} RUB",
            ]
        )
        if previous_snapshot is None:
            continue
        change = calculate_cbr_rate_change(rate, previous_snapshot.rates.get(code))
        if change is None:
            continue
        lines.extend(
            [
                f"Изменение: {_format_signed_rate(change.delta_rub)} RUB / {_format_signed_percent(change.delta_percent)}%",
                _format_change_direction(change),
            ]
        )
    return "\n".join(lines)


def is_cbr_update_check_window(now: datetime) -> bool:
    current_time = now.time()
    return CBR_UPDATE_CHECK_START <= current_time <= CBR_UPDATE_CHECK_END


async def check_cbr_update_notifications(
    bot: Bot,
    repo: UserRepository,
    cbr_service: CBRService,
    timezone_name: str,
    now: datetime | None = None,
) -> None:
    timezone = ZoneInfo(timezone_name)
    checked_at = now.astimezone(timezone) if now is not None else datetime.now(timezone)
    if not is_cbr_update_check_window(checked_at):
        return

    target_date = checked_at.date() + timedelta(days=1)
    try:
        snapshot = await cbr_service.fetch_rates(target_date)
    except Exception:
        logger.exception("CBR update notification fetch failed")
        return

    if snapshot.date < target_date:
        logger.info(
            "CBR update is not published yet: fetched %s for target %s",
            snapshot.date.isoformat(),
            target_date.isoformat(),
        )
        return

    previous_snapshot = await get_previous_cbr_rates(cbr_service, snapshot.date)
    if previous_snapshot is None:
        logger.warning("Could not find previous CBR rates before %s", snapshot.date.isoformat())

    text = format_cbr_update_notification(snapshot, previous_snapshot)
    keyboard = cbr_update_notification_keyboard()
    for user in repo.get_cbr_update_notification_users():
        if user.last_sent_cbr_date == snapshot.date:
            continue

        try:
            await bot.send_message(user.telegram_id, text, reply_markup=keyboard)
        except TelegramForbiddenError:
            logger.info("User %s blocked the bot; disabling CBR update notifications", user.telegram_id)
            repo.set_cbr_update_notifications(user.telegram_id, False)
        except TelegramAPIError:
            logger.exception("Could not send CBR update notification to %s", user.telegram_id)
        except Exception:
            logger.exception("Unexpected CBR update notification error for %s", user.telegram_id)
        else:
            repo.mark_cbr_update_notification_sent(user.telegram_id, snapshot.date)


async def send_daily_rates(
    bot: Bot,
    repo: UserRepository,
    cbr_service: CBRService,
    scheduler: AsyncIOScheduler,
    timezone_name: str,
    retry_count: int = 0,
    max_retries: int = DAILY_MAX_RETRIES,
    retry_delay_minutes: int = DAILY_RETRY_DELAY_MINUTES,
) -> None:
    timezone = ZoneInfo(timezone_name)
    today = datetime.now(timezone).date()

    try:
        snapshot = await cbr_service.get_rates_with_delta(today)
    except Exception:
        logger.exception("Daily CBR fetch failed")
        _schedule_retry(
            bot=bot,
            repo=repo,
            cbr_service=cbr_service,
            scheduler=scheduler,
            timezone=timezone,
            timezone_name=timezone_name,
            retry_count=retry_count,
            max_retries=max_retries,
            retry_delay_minutes=retry_delay_minutes,
        )
        return

    if snapshot.date != today:
        logger.info(
            "Latest CBR date is %s, not %s; scheduling retry",
            snapshot.date.isoformat(),
            today.isoformat(),
        )
        _schedule_retry(
            bot=bot,
            repo=repo,
            cbr_service=cbr_service,
            scheduler=scheduler,
            timezone=timezone,
            timezone_name=timezone_name,
            retry_count=retry_count,
            max_retries=max_retries,
            retry_delay_minutes=retry_delay_minutes,
        )
        return

    for user in repo.get_daily_users():
        if not user.currencies:
            logger.info("User %s has no selected currencies; skipping daily rates", user.telegram_id)
            continue

        if repo.was_daily_sent(user.telegram_id, snapshot.date):
            continue

        try:
            await bot.send_message(user.telegram_id, format_rates(snapshot, user.currencies))
        except TelegramForbiddenError:
            logger.info("User %s blocked the bot", user.telegram_id)
        except TelegramAPIError:
            logger.exception("Could not send daily rates to %s", user.telegram_id)
        except Exception:
            logger.exception("Unexpected daily delivery error for %s", user.telegram_id)
        else:
            repo.mark_daily_sent(user.telegram_id, snapshot.date)


def _schedule_retry(
    bot: Bot,
    repo: UserRepository,
    cbr_service: CBRService,
    scheduler: AsyncIOScheduler,
    timezone: ZoneInfo,
    timezone_name: str,
    retry_count: int,
    max_retries: int,
    retry_delay_minutes: int,
) -> None:
    if retry_count >= max_retries:
        logger.warning("Daily rates retry limit reached")
        return

    run_at = datetime.now(timezone) + timedelta(minutes=retry_delay_minutes)
    scheduler.add_job(
        send_daily_rates,
        trigger=DateTrigger(run_date=run_at, timezone=timezone),
        id=f"daily_rates_retry_{run_at.strftime('%Y%m%d%H%M%S')}_{retry_count + 1}",
        kwargs={
            "bot": bot,
            "repo": repo,
            "cbr_service": cbr_service,
            "scheduler": scheduler,
            "timezone_name": timezone_name,
            "retry_count": retry_count + 1,
            "max_retries": max_retries,
            "retry_delay_minutes": retry_delay_minutes,
        },
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=1800,
    )
