from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class UserSettings:
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    mode: str = "manual"
    daily_time: str = "18:10"
    timezone: str = "Europe/Moscow"
    currencies: list[str] = field(default_factory=list)
    cbr_update_notifications: bool = False
    last_sent_cbr_date: date | None = None


@dataclass(frozen=True)
class BotStats:
    total_users: int
    cbr_update_notifications: int
    new_24h: int
    new_7d: int


@dataclass(frozen=True)
class AdminUserRow:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    cbr_update_notifications: bool
    created_at: datetime
    updated_at: datetime
