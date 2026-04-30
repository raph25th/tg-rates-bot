# Telegram Currency Products

Проект готовится к разделению на два Telegram-продукта:

- `@kurs_rub_bot` — пользовательский калькулятор валют.
- `@rub_rates_bot` — профессиональный мониторинг курсов и ежедневные уведомления.

Сейчас реализуется основа для `@kurs_rub_bot`, а общая бизнес-логика вынесена в `core`.

## Что Уже Есть

- Python, aiogram 3, SQLite, APScheduler
- официальный источник ЦБ РФ: `https://www.cbr.ru/scripts/XML_daily.asp?date_req=DD/MM/YYYY`
- нормализация курсов: `code`, `name`, `nominal`, `value`, `unit_rate`, `date`
- валютный калькулятор по курсу ЦБ РФ
- форматирование денежных сумм с разделителями тысяч
- заготовка `core/live_rates.py` под будущий источник Investing
- настройки пользователя и выбор валют
- ежедневная отправка курсов для режима `daily`

## Архитектура

- `core/cbr.py` — получение и парсинг курсов ЦБ РФ
- `core/models.py` — общие модели курсов
- `core/converter.py` — парсинг пользовательского ввода и расчёт валют
- `core/money.py` — форматирование сумм, курсов и символов валют
- `core/live_rates.py` — интерфейс будущих live-курсов Investing
- `handlers/` — Telegram-сценарии
- `services/` — совместимые сервисные обёртки поверх `core`
- `db/` — SQLite-модели и репозиторий

## Сценарий `@kurs_rub_bot`

Пользователь вводит:

```text
10000 usd
100000 eur
1 000 000 rub usd
```

Бот распознаёт сумму и валюты, берёт текущий курс ЦБ РФ и отвечает сообщением, готовым к пересылке клиенту:

```text
💱 Расчёт валюты

10 000 USD по курсу ЦБ РФ:
= 755 273 ₽

Курс: 1 USD = 75,5273 ₽
Дата курса: 25.04.2026
Источник: ЦБ РФ

Сформировано через @kurs_rub_bot
```

После результата бот показывает inline-кнопки:

- `📊 Курсы сейчас`
- `⚙️ Источник курса`
- `🔁 Новый расчёт`

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Настройка

Создайте `.env` на основе `.env.example` и укажите токен BotFather:

```env
BOT_TOKEN=123456:your-token
DATABASE_URL=sqlite:///bot.db
DEFAULT_DAILY_TIME=18:10
TIMEZONE=Europe/Moscow
```

## Запуск

```powershell
python main.py
```

Для быстрой проверки токена и доступа к Telegram API:

```powershell
python main.py --health-check
```

При старте бот пишет в консоль диагностические строки:

```text
Routers included
Bot started
get_me ok: @your_bot
Polling started
```

Если `api.telegram.org` недоступен, приложение не падает, а пишет понятную ошибку `get_me failed` или `Polling failed` и повторяет попытку.

## Деплой на VPS

Для продакшен-запуска используйте Ubuntu VPS и systemd. Подробная инструкция лежит в [`deploy/README_DEPLOY.md`](deploy/README_DEPLOY.md), пример unit-файла — в [`deploy/systemd/tg-rates-bot.service.example`](deploy/systemd/tg-rates-bot.service.example), пример production env — в [`.env.production.example`](.env.production.example).

На локальной Windows-машине, особенно при VPN или нестабильном маршруте, `aiogram/aiohttp` может получать ошибки вида `ClientConnectorError: Cannot connect to host api.telegram.org:443 ssl:default [Превышен таймаут семафора]`. Это не проблема роутеров бота: для проверки используйте `python main.py --health-check`, а для стабильной работы выносите процесс на VPS с прямым исходящим HTTPS-доступом к `api.telegram.org:443`.

## Тесты

```powershell
pytest
```

## Как подключить Investing.com

У Investing.com нет официального публичного API, поэтому live-курсы вынесены в отдельный market-provider слой. Бот не хардкодит Investing в handlers: источник можно заменить без переписывания сценариев.

Поддерживаемые режимы:

- `disabled` — live-курсы выключены, бот показывает понятную ошибку.
- `mock` — тестовый provider с фиксированными курсами, удобно для проверки интерфейса.
- `investing_rapidapi` — каркас под RapidAPI-провайдера Investing.
- `investing_apify` — каркас под Apify actor/task.
- `investing_scraper` — каркас под прямой scraper, пока без реального парсинга.

Переменные окружения:

```env
MARKET_RATE_PROVIDER=mock
INVESTING_PROVIDER_MODE=mock
INVESTING_RAPIDAPI_KEY=
INVESTING_APIFY_TOKEN=
```

Для production по умолчанию оставляйте `disabled`, пока не выбран конкретный поставщик данных. Если ключ RapidAPI или Apify не задан, бот не падает и отвечает: `Курсы Investing временно недоступны. Проверьте настройки источника.`

Поддерживаемые пары:

```text
USD/RUB, EUR/RUB, CNY/RUB, GBP/RUB, AED/RUB, THB/RUB, KRW/RUB, JPY/RUB
```

Live-курсы кэшируются на 60 секунд, чтобы не дергать внешний источник при каждом клике.
