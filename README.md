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

## Запуск локально

1. Скопируйте `.env.example` в `.env` и заполните переменные.
2. Установите зависимости:

```bash
pip install -r requirements.txt
```

3. Запустите бота:

```bash
python main.py
```

## Запуск через Docker / VPS

Этот вариант подходит для обычного VPS с Docker и Docker Compose.

1. Скопируйте `.env.example` в `.env` и заполните переменные.
2. Создайте папку для данных:

```bash
mkdir -p data
```

3. Соберите и запустите контейнер:

```bash
docker compose up -d --build
```

4. Посмотреть логи:

```bash
docker compose logs -f
```

5. Остановить контейнер:

```bash
docker compose down
```

Контейнер хранит SQLite-базу в `./data`, поэтому данные сохраняются между перезапусками.

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
# заполни BOT_TOKEN / MANAGER_CHAT_ID / ADMIN_IDS / TG_PROXY_URL
mkdir -p data
docker compose up -d --build
```
