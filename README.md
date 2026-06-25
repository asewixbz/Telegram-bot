# Telegram bot первичной обработки лидов

MVP Telegram-бота для миграционных услуг:

- пошаговая квалификация лидов;
- сбор согласия на обработку данных;
- сбор цели, гражданства, страны проживания, страны назначения, сроков, бюджета и контакта;
- классификация лида как `hot / warm / cold`;
- сохранение состояния между сообщениями в SQLite;
- уведомление менеджера и отправка webhook JSON при завершении анкеты;
- приём документов после завершения анкеты;
- админ-команды для менеджера.

## Быстрый старт на Ubuntu через Docker

Ниже — самый простой вариант установки: сначала ставим Docker, потом одной цепочкой скачиваем репозиторий, создаём `.env` и запускаем бота.

### 1) Установить Docker и Git

```bash
sudo apt update && sudo apt install -y git curl ca-certificates docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker
```

### 2) Скачать репозиторий

```bash
git clone https://github.com/Asewixbz/Telegram-bot.git
cd Telegram-bot
```

Если Docker уже установлен, можно сразу выполнить короткий вариант:

```bash
git clone https://github.com/Asewixbz/Telegram-bot.git && cd Telegram-bot
```

### 3) Создать `.env` и добавить токены/ключи

Сначала можно скопировать шаблон:

```bash
cp .env.example .env
```

Дальше удобно заполнить секреты через переменные окружения и сразу записать их в `.env`:

```bash
export BOT_TOKEN="123456:ABCDEF"
export MANAGER_CHAT_ID="123456789"
export LEAD_WEBHOOK_URL="https://example.com/lead-completed"
export TG_PROXY_URL=""
export ADMIN_IDS="123456789,987654321"

cat > .env <<EOF
BOT_TOKEN=$BOT_TOKEN
DB_PATH=data/leads.sqlite3
MANAGER_CHAT_ID=$MANAGER_CHAT_ID
LEAD_WEBHOOK_URL=$LEAD_WEBHOOK_URL
TG_PROXY_URL=$TG_PROXY_URL
ADMIN_IDS=$ADMIN_IDS
ENTRY_SOURCE=video_01
UTM_SOURCE=youtube
UTM_CAMPAIGN=migration_video_a
RESPONSE_ETA=в течение 15 минут
EOF
```

Если нужно поменять только отдельные значения, можно сделать это точечно:

```bash
sed -i 's|^BOT_TOKEN=.*|BOT_TOKEN=123456:ABCDEF|' .env
sed -i 's|^MANAGER_CHAT_ID=.*|MANAGER_CHAT_ID=123456789|' .env
sed -i 's|^LEAD_WEBHOOK_URL=.*|LEAD_WEBHOOK_URL=https://example.com/lead-completed|' .env
sed -i 's|^TG_PROXY_URL=.*|TG_PROXY_URL=socks5://user:pass@host:port|' .env
sed -i 's|^ADMIN_IDS=.*|ADMIN_IDS=123456789,987654321|' .env
```

### 4) Создать папку для данных и запустить бота

```bash
mkdir -p data
docker compose up -d --build
```

### 5) Смотреть логи и остановить контейнер

```bash
docker compose logs -f
```

```bash
docker compose down
```

Контейнер хранит SQLite-базу в `./data`, поэтому данные сохраняются между перезапусками.

## Запуск локально без Docker

1. Скопируйте `.env.example` в `.env` и заполните переменные.
2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Запустите бота:

```bash
python main.py
```

## Переменные окружения

- `BOT_TOKEN` — токен Telegram-бота
- `DB_PATH` — путь к SQLite базе
- `MANAGER_CHAT_ID` — чат или личный чат менеджера для уведомлений
- `LEAD_WEBHOOK_URL` — URL для `lead_completed` webhook
- `TG_PROXY_URL` — proxy URL для Telegram API, если VPS не может достучаться до `api.telegram.org` напрямую
- `ADMIN_IDS` — список Telegram user ID через запятую для команд `/leads`, `/hot`, `/warm`, `/cold`, `/lead`, `/note`, `/done`
- `ENTRY_SOURCE` — источник по умолчанию, если `/start` пришёл без payload
- `UTM_SOURCE` — UTM source по умолчанию
- `UTM_CAMPAIGN` — UTM campaign по умолчанию
- `RESPONSE_ETA` — текст для сообщения на финальном шаге

## Proxy support

Если ваш VPS не может достучаться до `api.telegram.org` напрямую, можно задать `TG_PROXY_URL`.

Поддерживаются HTTP(S) и SOCKS5-прокси.

Примеры:

```text
TG_PROXY_URL=http://user:pass@host:port
TG_PROXY_URL=socks5://user:pass@host:port
```

## Production hardening

Рекомендуемый порядок на VPS:

```bash
cp .env.example .env
# заполните BOT_TOKEN / MANAGER_CHAT_ID / ADMIN_IDS / TG_PROXY_URL
mkdir -p data
docker compose up -d --build
```
