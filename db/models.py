from dataclasses import dataclass, field


@dataclass(frozen=True)
class UserSettings:
    telegram_id: int
    mode: str = "manual"
    daily_time: str = "18:10"
    timezone: str = "Europe/Moscow"
    currencies: list[str] = field(default_factory=list)
