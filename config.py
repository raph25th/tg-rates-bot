import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is declared for runtime
    load_dotenv = None


def parse_daily_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        raise ValueError("DEFAULT_DAILY_TIME must use HH:MM format") from exc

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("DEFAULT_DAILY_TIME must be a valid 24-hour time")
    return hour, minute


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str = "sqlite:///bot.db"
    default_daily_time: str = "18:10"
    timezone: str = "Europe/Moscow"
    market_rate_provider: str = "disabled"
    investing_provider_mode: str = "disabled"
    investing_rapidapi_key: str = ""
    investing_apify_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        if load_dotenv is not None:
            load_dotenv()

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise ValueError("BOT_TOKEN is required. Put it in .env or export it.")

        settings = cls(
            bot_token=bot_token,
            database_url=os.getenv("DATABASE_URL", "sqlite:///bot.db").strip(),
            default_daily_time=os.getenv("DEFAULT_DAILY_TIME", "18:10").strip(),
            timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip(),
            market_rate_provider=os.getenv("MARKET_RATE_PROVIDER", "disabled").strip(),
            investing_provider_mode=os.getenv("INVESTING_PROVIDER_MODE", "disabled").strip(),
            investing_rapidapi_key=os.getenv("INVESTING_RAPIDAPI_KEY", os.getenv("RAPIDAPI_KEY", "")).strip(),
            investing_apify_token=os.getenv("INVESTING_APIFY_TOKEN", os.getenv("APIFY_TOKEN", "")).strip(),
        )
        settings.validate()
        return settings

    @property
    def database_path(self) -> str:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported")
        path = self.database_url.removeprefix(prefix)
        return path or "bot.db"

    def validate(self) -> None:
        parse_daily_time(self.default_daily_time)
        ZoneInfo(self.timezone)
        allowed_providers = {"", "disabled", "mock", "yahoo", "investing_rapidapi", "investing_apify", "investing_scraper"}
        if self.market_rate_provider not in allowed_providers:
            raise ValueError("MARKET_RATE_PROVIDER must be disabled, mock, yahoo, investing_rapidapi, investing_apify or investing_scraper")
        if self.investing_provider_mode not in allowed_providers:
            raise ValueError("INVESTING_PROVIDER_MODE must be disabled, mock, yahoo, investing_rapidapi, investing_apify or investing_scraper")
