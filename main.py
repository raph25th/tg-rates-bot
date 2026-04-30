import argparse
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError

from config import Settings
from db.repo import UserRepository
from handlers import converter, rates, settings as settings_handlers
from handlers.start import router as start_router
from services.cbr import CBRService
from services.rates.market import build_market_rate_provider
from services.scheduler import setup_scheduler

logger = logging.getLogger(__name__)
POLLING_RETRY_DELAY_SECONDS = 15


async def delete_webhook_safely(bot: Bot) -> None:
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except TelegramNetworkError as exc:
        print(f"delete_webhook failed due to network issue: {exc}. Continue with polling.", flush=True)
        logger.warning(
            "Telegram network is unavailable while deleting webhook: %s. "
            "Continue with polling.",
            exc,
        )
    except TelegramAPIError as exc:
        print(f"delete_webhook failed due to Telegram API error: {exc}. Continue with polling.", flush=True)
        logger.warning(
            "Telegram API returned an error while deleting webhook: %s. "
            "Continue with polling.",
            exc,
        )
    except Exception:
        print("delete_webhook failed unexpectedly. Continue with polling.", flush=True)
        logger.exception("Unexpected error while deleting webhook. Continue with polling.")


async def wait_for_telegram_api(bot: Bot) -> None:
    while True:
        try:
            me = await bot.get_me()
            logger.info("Telegram API is available. Bot: @%s", me.username)
            print(f"get_me ok: @{me.username}", flush=True)
            return
        except TelegramNetworkError as exc:
            print(
                f"get_me failed: Telegram network is unavailable: {exc}. "
                f"Retry in {POLLING_RETRY_DELAY_SECONDS} seconds.",
                flush=True,
            )
            logger.warning(
                "Telegram API is not reachable: %s. Retry in %s seconds.",
                exc,
                POLLING_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(POLLING_RETRY_DELAY_SECONDS)
        except TelegramAPIError as exc:
            print(
                f"get_me failed: Telegram API returned an error: {exc}. "
                f"Retry in {POLLING_RETRY_DELAY_SECONDS} seconds.",
                flush=True,
            )
            logger.warning(
                "Telegram API returned an error during startup check: %s. "
                "Retry in %s seconds.",
                exc,
                POLLING_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(POLLING_RETRY_DELAY_SECONDS)
        except Exception as exc:
            print(
                f"get_me failed unexpectedly: {exc}. "
                f"Retry in {POLLING_RETRY_DELAY_SECONDS} seconds.",
                flush=True,
            )
            logger.exception(
                "Unexpected error during startup check. Retry in %s seconds.",
                POLLING_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(POLLING_RETRY_DELAY_SECONDS)


async def start_polling_safely(
    dp: Dispatcher,
    bot: Bot,
    repo: UserRepository,
    cbr_service: CBRService,
    app_config: Settings,
    market_rate_provider,
) -> None:
    while True:
        try:
            await wait_for_telegram_api(bot)
            logger.info("Starting Telegram polling...")
            print("Polling started", flush=True)
            await dp.start_polling(
                bot,
                repo=repo,
                cbr_service=cbr_service,
                app_config=app_config,
                market_rate_provider=market_rate_provider,
            )
            return
        except TelegramNetworkError as exc:
            print(
                f"Polling failed: Telegram network is unavailable: {exc}. "
                f"Retry in {POLLING_RETRY_DELAY_SECONDS} seconds.",
                flush=True,
            )
            logger.warning(
                "Telegram network is unavailable while starting polling: %s. "
                "Retry in %s seconds.",
                exc,
                POLLING_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(POLLING_RETRY_DELAY_SECONDS)
        except TelegramAPIError as exc:
            print(
                f"Polling failed: Telegram API returned an error: {exc}. "
                f"Retry in {POLLING_RETRY_DELAY_SECONDS} seconds.",
                flush=True,
            )
            logger.warning(
                "Telegram API returned an error while starting polling: %s. "
                "Retry in %s seconds.",
                exc,
                POLLING_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(POLLING_RETRY_DELAY_SECONDS)
        except Exception as exc:
            print(
                f"Polling failed unexpectedly: {exc}. "
                f"Retry in {POLLING_RETRY_DELAY_SECONDS} seconds.",
                flush=True,
            )
            logger.exception(
                "Unexpected error while starting polling. Retry in %s seconds.",
                POLLING_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(POLLING_RETRY_DELAY_SECONDS)


async def run_health_check() -> int:
    try:
        app_config = Settings.from_env()
    except Exception as exc:
        print(f"Health check failed: invalid configuration: {exc}", flush=True)
        logger.exception("Health check failed: invalid configuration")
        return 1

    bot = Bot(token=app_config.bot_token)

    try:
        me = await bot.get_me()
    except TelegramNetworkError as exc:
        print(f"Health check failed: api.telegram.org is unavailable: {exc}", flush=True)
        logger.warning("Health check failed: Telegram network is unavailable: %s", exc)
        return 1
    except TelegramAPIError as exc:
        print(f"Health check failed: Telegram API returned an error: {exc}", flush=True)
        logger.warning("Health check failed: Telegram API returned an error: %s", exc)
        return 1
    except Exception as exc:
        print(f"Health check failed unexpectedly: {exc}", flush=True)
        logger.exception("Health check failed unexpectedly")
        return 1
    finally:
        await bot.session.close()

    print(f"Health check ok: Telegram API is available. Bot: @{me.username}", flush=True)
    logger.info("Health check ok: Telegram API is available. Bot: @%s", me.username)
    return 0


async def run() -> None:
    app_config = Settings.from_env()
    repo = UserRepository(
        database_path=app_config.database_path,
        default_daily_time=app_config.default_daily_time,
        default_timezone=app_config.timezone,
    )
    repo.init()

    bot = Bot(token=app_config.bot_token)
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(rates.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(converter.router)
    logger.info("Routers included")
    print("Routers included", flush=True)

    cbr_service = CBRService()
    market_rate_provider = build_market_rate_provider(app_config)
    scheduler = setup_scheduler(
        bot=bot,
        repo=repo,
        cbr_service=cbr_service,
        app_config=app_config,
    )
    scheduler.start()

    try:
        logger.info("Bot started (production)")
        print("Bot started (production)", flush=True)
        await delete_webhook_safely(bot)
        await start_polling_safely(
            dp=dp,
            bot=bot,
            repo=repo,
            cbr_service=cbr_service,
            app_config=app_config,
            market_rate_provider=market_rate_provider,
        )
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Telegram rates bot")
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Check BOT_TOKEN and Telegram API availability with bot.get_me(), then exit.",
    )
    args = parser.parse_args()

    if args.health_check:
        raise SystemExit(asyncio.run(run_health_check()))

    asyncio.run(run())


if __name__ == "__main__":
    main()
