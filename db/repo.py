from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Iterable

from db.models import UserSettings
from services.formatter import normalize_currency_codes

VALID_MODES = {"daily", "manual"}


class UserRepository:
    def __init__(
        self,
        database_path: str,
        default_daily_time: str = "18:10",
        default_timezone: str = "Europe/Moscow",
    ) -> None:
        self.database_path = database_path
        self.default_daily_time = default_daily_time
        self.default_timezone = default_timezone

    def _connect(self) -> sqlite3.Connection:
        if self.database_path != ":memory:":
            parent = Path(self.database_path).expanduser().parent
            if str(parent) not in {"", "."}:
                parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if self.database_path != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def init(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    mode TEXT NOT NULL DEFAULT 'manual',
                    daily_time TEXT NOT NULL DEFAULT '18:10',
                    timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS user_currencies (
                    telegram_id INTEGER NOT NULL,
                    currency_code TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, currency_code),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS daily_deliveries (
                    telegram_id INTEGER NOT NULL,
                    rate_date TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (telegram_id, rate_date),
                    FOREIGN KEY (telegram_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                );
                """
            )
            self._ensure_users_column(
                connection,
                "cbr_update_notifications",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_users_column(
                connection,
                "last_sent_cbr_date",
                "TEXT",
            )

    def ensure_user(self, telegram_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO users (telegram_id, mode, daily_time, timezone)
                VALUES (?, 'manual', ?, ?)
                ON CONFLICT(telegram_id) DO NOTHING
                """,
                (telegram_id, self.default_daily_time, self.default_timezone),
            )

    def get_user_settings(self, telegram_id: int) -> UserSettings:
        self.ensure_user(telegram_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT telegram_id, mode, daily_time, timezone, cbr_update_notifications, last_sent_cbr_date
                FROM users
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            ).fetchone()
            currencies = self._get_currencies(connection, telegram_id)

        return UserSettings(
            telegram_id=row["telegram_id"],
            mode=row["mode"],
            daily_time=row["daily_time"],
            timezone=row["timezone"],
            currencies=currencies,
            cbr_update_notifications=bool(row["cbr_update_notifications"]),
            last_sent_cbr_date=_parse_date(row["last_sent_cbr_date"]),
        )

    def set_mode(self, telegram_id: int, mode: str) -> UserSettings:
        if mode not in VALID_MODES:
            raise ValueError(f"Unknown mode: {mode}")

        self.ensure_user(telegram_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET mode = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (mode, telegram_id),
            )
        return self.get_user_settings(telegram_id)

    def get_currencies(self, telegram_id: int) -> list[str]:
        self.ensure_user(telegram_id)
        with self._connect() as connection:
            return self._get_currencies(connection, telegram_id)

    def set_currencies(self, telegram_id: int, codes: Iterable[str]) -> UserSettings:
        self.ensure_user(telegram_id)
        normalized = normalize_currency_codes(codes)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM user_currencies WHERE telegram_id = ?",
                (telegram_id,),
            )
            connection.executemany(
                """
                INSERT INTO user_currencies (telegram_id, currency_code)
                VALUES (?, ?)
                """,
                [(telegram_id, code) for code in normalized],
            )
            connection.execute(
                """
                UPDATE users
                SET updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
        return self.get_user_settings(telegram_id)

    def toggle_currency(self, telegram_id: int, code: str) -> UserSettings:
        self.ensure_user(telegram_id)
        code = code.strip().upper()
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT 1
                FROM user_currencies
                WHERE telegram_id = ? AND currency_code = ?
                """,
                (telegram_id, code),
            ).fetchone()
            if existing:
                connection.execute(
                    """
                    DELETE FROM user_currencies
                    WHERE telegram_id = ? AND currency_code = ?
                    """,
                    (telegram_id, code),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO user_currencies (telegram_id, currency_code)
                    VALUES (?, ?)
                    """,
                    (telegram_id, code),
                )
            connection.execute(
                """
                UPDATE users
                SET updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (telegram_id,),
            )
        return self.get_user_settings(telegram_id)

    def get_daily_users(self) -> list[UserSettings]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT telegram_id, mode, daily_time, timezone, cbr_update_notifications, last_sent_cbr_date
                FROM users
                WHERE mode = 'daily'
                ORDER BY telegram_id
                """
            ).fetchall()
            return [
                UserSettings(
                    telegram_id=row["telegram_id"],
                    mode=row["mode"],
                    daily_time=row["daily_time"],
                    timezone=row["timezone"],
                    currencies=self._get_currencies(connection, row["telegram_id"]),
                    cbr_update_notifications=bool(row["cbr_update_notifications"]),
                    last_sent_cbr_date=_parse_date(row["last_sent_cbr_date"]),
                )
                for row in rows
            ]

    def set_cbr_update_notifications(self, telegram_id: int, enabled: bool) -> UserSettings:
        self.ensure_user(telegram_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET cbr_update_notifications = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (1 if enabled else 0, telegram_id),
            )
        return self.get_user_settings(telegram_id)

    def get_cbr_update_notification_users(self) -> list[UserSettings]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT telegram_id, mode, daily_time, timezone, cbr_update_notifications, last_sent_cbr_date
                FROM users
                WHERE cbr_update_notifications = 1
                ORDER BY telegram_id
                """
            ).fetchall()
            return [
                UserSettings(
                    telegram_id=row["telegram_id"],
                    mode=row["mode"],
                    daily_time=row["daily_time"],
                    timezone=row["timezone"],
                    currencies=self._get_currencies(connection, row["telegram_id"]),
                    cbr_update_notifications=bool(row["cbr_update_notifications"]),
                    last_sent_cbr_date=_parse_date(row["last_sent_cbr_date"]),
                )
                for row in rows
            ]

    def mark_cbr_update_notification_sent(self, telegram_id: int, rate_date: date) -> None:
        self.ensure_user(telegram_id)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE users
                SET last_sent_cbr_date = ?, updated_at = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (rate_date.isoformat(), telegram_id),
            )

    def was_daily_sent(self, telegram_id: int, rate_date: date) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM daily_deliveries
                WHERE telegram_id = ? AND rate_date = ?
                """,
                (telegram_id, rate_date.isoformat()),
            ).fetchone()
            return row is not None

    def mark_daily_sent(self, telegram_id: int, rate_date: date) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO daily_deliveries (telegram_id, rate_date)
                VALUES (?, ?)
                """,
                (telegram_id, rate_date.isoformat()),
            )

    def _get_currencies(
        self,
        connection: sqlite3.Connection,
        telegram_id: int,
    ) -> list[str]:
        rows = connection.execute(
            """
            SELECT currency_code
            FROM user_currencies
            WHERE telegram_id = ?
            ORDER BY created_at, currency_code
            """,
            (telegram_id,),
        ).fetchall()
        return normalize_currency_codes(row["currency_code"] for row in rows)

    def _ensure_users_column(
        self,
        connection: sqlite3.Connection,
        column_name: str,
        column_definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if column_name not in columns:
            connection.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)
