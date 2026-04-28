# Деплой на VPS Ubuntu 24.04

Инструкция описывает production-запуск Telegram-бота через `systemd`.

## 1. Подключение к серверу

```bash
ssh root@YOUR_SERVER_IP
```

## 2. Установка системных зависимостей

```bash
apt update
apt install python3 python3-venv python3-pip git -y
```

## 3. Клонирование проекта

```bash
cd /root
git clone <REPO_URL> tg-rates-bot
cd /root/tg-rates-bot
```

Если проект копируется вручную, положите файлы проекта в `/root/tg-rates-bot`.

## 4. Создание venv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 5. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Создание `.env`

```bash
cp .env.production.example .env
nano .env
```

Минимальное содержимое:

```env
BOT_TOKEN=123456:your-production-token
TIMEZONE=Europe/Moscow
```

Файл `.env` содержит секреты и не должен попадать в репозиторий.

## 7. Проверка

```bash
python main.py --health-check
```

Успешный ответ:

```text
Health check ok: Telegram API is available. Bot: @your_bot
```

Если проверка не проходит, проверьте токен и доступ сервера к `api.telegram.org:443`.

## 8. Копирование systemd-файла

```bash
cp deploy/systemd/tg-rates-bot.service.example /etc/systemd/system/tg-rates-bot.service
```

## 9. Перезагрузка systemd

```bash
systemctl daemon-reexec
systemctl daemon-reload
```

## 10. Запуск

```bash
systemctl start tg-rates-bot
systemctl enable tg-rates-bot
```

Проверить статус:

```bash
systemctl status tg-rates-bot --no-pager
```

## 11. Логи

```bash
journalctl -u tg-rates-bot -f
```

При нормальном запуске в логах должны появиться строки:

```text
Bot started (production)
get_me ok: @your_bot
Polling started
```

## Обновление проекта

```bash
cd /root/tg-rates-bot
git pull
source .venv/bin/activate
pip install -r requirements.txt
systemctl restart tg-rates-bot
journalctl -u tg-rates-bot -f
```

## Диагностика

- Если `python main.py --health-check` падает, проверьте `BOT_TOKEN` и доступ к Telegram API.
- Если service не стартует, смотрите `journalctl -u tg-rates-bot -n 100 --no-pager`.
- Если меняли `.env`, выполните `systemctl restart tg-rates-bot`.
- `Restart=always` в systemd автоматически поднимет процесс после падения.
