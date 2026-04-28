from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from config import Settings, parse_daily_time
from db.repo import UserRepository
from services.cbr import CBRService
from services.formatter import format_rates

logger = logging.getLogger(__name__)

DAILY_RETRY_DELAY_MINUTES = 15
DAILY_MAX_RETRIES = 24


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
    return scheduler


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
