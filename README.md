# Telegram Currency Products

Проект готовится к разделению на два Telegram-продукта:

- `@kurs_rub_bot` — пользовательский калькулятор валют.
- `@rub_rates_bot` — профессиональный мониторинг курсов и ежедневные уведомления.

Сейчас реализуется основа для `@kurs_rub_bot`.

## Возможности

- Python, aiogram 3, SQLite, APScheduler.
- Официальные курсы ЦБ РФ через `https://www.cbr.ru/scripts/XML_daily.asp?date_req=DD/MM/YYYY`.
- Валютный калькулятор: валюта → рубли и рубли → валюта.
- Процентная корректировка к курсу.
- Поддержка USD, EUR, CNY, GBP, AED, THB, KRW, JPY.
- Рыночный provider-слой для Yahoo Finance, mock-режима и будущих источников.
- Кэширование market-курсов на 60 секунд.
- systemd-ready деплой на VPS.

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Настройка

Создайте `.env` на основе `.env.example`:

```env
BOT_TOKEN=123456:your-token
DATABASE_URL=sqlite:///bot.db
DEFAULT_DAILY_TIME=18:10
TIMEZONE=Europe/Moscow
MARKET_RATE_PROVIDER=yahoo
INVESTING_PROVIDER_MODE=disabled
```

## Запуск

```powershell
python main.py
```

Проверка токена и доступа к Telegram API:

```powershell
python main.py --health-check
```

## Рыночный курс

Рыночный курс используется как ориентир для предварительных расчётов. На первом этапе источник — Yahoo Finance. Значения могут немного отличаться от Investing и других площадок, так как live-курсы обновляются в течение дня.

Основной режим:

```env
MARKET_RATE_PROVIDER=yahoo
```

Источник в сообщениях бота:

```text
Yahoo Finance / рыночный ориентир
```

Если Yahoo Finance временно недоступен, бот не падает и показывает:

```text
Рыночные курсы временно недоступны.
Попробуйте позже или используйте курс ЦБ РФ.
```

Для проверки интерфейса без внешнего источника:

```env
MARKET_RATE_PROVIDER=mock
```

В mock-режиме бот явно показывает, что данные тестовые:

```text
Источник: Mock Market / тестовый режим

⚠️ Тестовый режим
Это не реальные рыночные курсы. Данные используются для проверки интерфейса.
```

Поддерживаемые Yahoo Finance тикеры:

```text
USD/RUB: RUB=X
EUR/RUB: EURRUB=X
CNY/RUB: CNYRUB=X
GBP/RUB: GBPRUB=X
AED/RUB: AEDRUB=X
THB/RUB: THBRUB=X
KRW/RUB: KRWRUB=X
JPY/RUB: JPYRUB=X
```

Если прямой тикер недоступен, provider для части валют использует fallback через USD:

```text
JPY/RUB = RUB=X / JPY=X
THB/RUB = RUB=X / THB=X
CNY/RUB = RUB=X / CNY=X
```

## Деплой на VPS

Подробная инструкция лежит в [`deploy/README_DEPLOY.md`](deploy/README_DEPLOY.md), пример systemd unit — в [`deploy/systemd/tg-rates-bot.service.example`](deploy/systemd/tg-rates-bot.service.example).

После обновления на сервере:

```bash
cd /root/tg-rates-bot
source .venv/bin/activate
pip install -r requirements.txt
python main.py --health-check
systemctl restart tg-rates-bot
journalctl -u tg-rates-bot -f
```

## Тесты

```powershell
python -m pytest
```
