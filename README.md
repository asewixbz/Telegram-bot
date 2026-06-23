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

## Запуск

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
- `ADMIN_IDS` — список Telegram user ID через запятую для команд `/leads`, `/hot`, `/warm`, `/cold`, `/lead`, `/note`, `/done`
- `ENTRY_SOURCE` — источник по умолчанию, если `/start` пришёл без payload
- `UTM_SOURCE` — UTM source по умолчанию
- `UTM_CAMPAIGN` — UTM campaign по умолчанию
- `RESPONSE_ETA` — текст для сообщения на финальном шаге

## Логика старта

Команда `/start` создаёт новую заявку или предлагает продолжить незавершённую.
Дополнительно бот принимает payload вида:

```text
/start video_01|youtube|migration_video_a
```

или

```text
/start entry_source=video_01&utm_source=youtube&utm_campaign=migration_video_a
```

## Хранение данных

Данные заявок, файлов и комментариев хранятся в SQLite и не теряются между перезапусками.
