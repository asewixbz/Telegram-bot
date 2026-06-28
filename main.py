from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STEP_SERVICE = "service"
STEP_COUNTRY = "country"
STEP_CITY = "city"
STEP_TIMELINE = "timeline"
STEP_DOCS = "docs"
STEP_PURPOSE = "purpose"
STEP_MAIN_CONTACT = "main_contact"
STEP_ADDITIONAL_CONTACT = "additional_contact"
STEP_CONFIRM = "confirm"
STEP_DONE = "done"
STEP_ABANDONED = "abandoned"

STEP_SEQUENCE = [
    STEP_SERVICE,
    STEP_COUNTRY,
    STEP_CITY,
    STEP_TIMELINE,
    STEP_DOCS,
    STEP_PURPOSE,
    STEP_MAIN_CONTACT,
    STEP_ADDITIONAL_CONTACT,
    STEP_CONFIRM,
    STEP_DONE,
]

STEP_TO_FIELD = {
    STEP_SERVICE: "service",
    STEP_COUNTRY: "departure_country",
    STEP_CITY: "departure_city",
    STEP_TIMELINE: "timeline",
    STEP_DOCS: "documents",
    STEP_PURPOSE: "purpose",
    STEP_MAIN_CONTACT: "main_contact",
    STEP_ADDITIONAL_CONTACT: "additional_contact",
}

NAV_BACK = "⬅️ Назад"
NAV_MENU = "🏠 Главное меню"
NAV_NEW = "➕ Новая заявка"
NAV_SKIP = "⏭ Пропустить"
CONFIRM_TEXT = "✅ Подтвердить заявку"
EDIT_TEXT = "✏️ Изменить выбор"
SHARE_CONTACT_TEXT = "📱 Поделиться номером"

SERVICE_OPTIONS = [
    ("🚶 Въезд в Россию", "entry"),
    ("🛂 Пересечение границы", "border"),
    ("💬 Консультация", "consult"),
    ("📄 Документы", "documents"),
    ("❓ Другое", "other"),
]

COUNTRY_OPTIONS = [
    ("🇺🇿 Узбекистан", "uzbekistan"),
    ("🇹🇯 Таджикистан", "tajikistan"),
    ("🇰🇬 Кыргызстан", "kyrgyzstan"),
    ("🇰🇿 Казахстан", "kazakhstan"),
    ("🌍 Другая страна", "other"),
]

CITY_OPTIONS_BY_COUNTRY = {
    "uzbekistan": [("Ташкент", "tashkent"), ("Самарканд", "samarkand"), ("Бухара", "bukhara"), ("Фергана", "fergana"), ("📍 Другое", "other")],
    "tajikistan": [("Душанбе", "dushanbe"), ("Худжанд", "khujand"), ("Бохтар", "bokhtar"), ("Куляб", "kulob"), ("📍 Другое", "other")],
    "kyrgyzstan": [("Бишкек", "bishkek"), ("Ош", "osh"), ("Джалал-Абад", "jalal_abad"), ("Каракол", "karakol"), ("📍 Другое", "other")],
    "kazakhstan": [("Алматы", "almaty"), ("Астана", "astana"), ("Шымкент", "shymkent"), ("Караганда", "karaganda"), ("📍 Другое", "other")],
    "other": [("📍 Другое", "other")],
}

TIMELINE_OPTIONS = [
    ("🚨 Сегодня", "today"),
    ("1–3 дня", "1_3_days"),
    ("📅 На этой неделе", "this_week"),
    ("🕓 Позже", "later"),
    ("⏱ Срочно", "urgent"),
]

DOCS_OPTIONS = [
    ("🛂 Паспорт есть", "passport"),
    ("📇 Миграционная карта есть", "migration_card"),
    ("🛂 Виза есть", "visa"),
    ("🧩 Нужна полная помощь", "full_help"),
    ("❓ Не знаю", "unknown"),
]

PURPOSE_OPTIONS = [
    ("💼 Работа", "work"),
    ("👨‍👩‍👧‍👦 Семья", "family"),
    ("🎓 Учёба", "study"),
    ("✈️ Туризм", "tourism"),
    ("❓ Другое", "other"),
]

GOAL_OPTIONS = [
    ("ВНЖ", "vnj"),
    ("ПМЖ", "pmzh"),
    ("Виза", "visa"),
    ("Гражданство", "citizenship"),
    ("Работа", "work"),
    ("Учёба", "study"),
    ("Семья / воссоединение", "family"),
    ("Другое", "other"),
]
GOAL_BY_TOKEN = {token: label for label, token in GOAL_OPTIONS}
GOAL_ALIASES = {
    "внж": "ВНЖ",
    "вид на жительство": "ВНЖ",
    "пмж": "ПМЖ",
    "постоянное место жительства": "ПМЖ",
    "виза": "Виза",
    "гражданство": "Гражданство",
    "работа": "Работа",
    "трудоустройство": "Работа",
    "учеба": "Учёба",
    "учёба": "Учёба",
    "семья": "Семья / воссоединение",
    "воссоединение": "Семья / воссоединение",
    "другое": "Другое",
}

TIMELINE_COMPAT_OPTIONS = [
    ("Срочно", "urgent"),
    ("1–3 месяца", "m1_3"),
    ("3–6 месяцев", "m3_6"),
    ("Пока изучаю варианты", "researching"),
]
TIMELINE_BY_TOKEN = {token: label for label, token in TIMELINE_COMPAT_OPTIONS}
TIMELINE_ALIASES = {
    "срочно": "Срочно",
    "1 3 месяца": "1–3 месяца",
    "1-3 месяца": "1–3 месяца",
    "1–3 месяца": "1–3 месяца",
    "3 6 месяцев": "3–6 месяцев",
    "3-6 месяцев": "3–6 месяцев",
    "3–6 месяцев": "3–6 месяцев",
    "пока изучаю варианты": "Пока изучаю варианты",
    "изучаю варианты": "Пока изучаю варианты",
}

BUDGET_OPTIONS = [
    ("До 1 000 €", "under_1000"),
    ("1 000–3 000 €", "1000_3000"),
    ("3 000–7 000 €", "3000_7000"),
    ("7 000 €+", "7000_plus"),
    ("Пока не знаю", "unknown"),
]
BUDGET_BY_TOKEN = {token: label for label, token in BUDGET_OPTIONS}
BUDGET_ALIASES = {
    "до 1 000 €": "До 1 000 €",
    "до 1000 €": "До 1 000 €",
    "1000 3000 €": "1 000–3 000 €",
    "1 000 3 000 €": "1 000–3 000 €",
    "3000 7000 €": "3 000–7 000 €",
    "3 000 7 000 €": "3 000–7 000 €",
    "7 000 €+": "7 000 €+",
    "7000 €+": "7 000 €+",
    "пока не знаю": "Пока не знаю",
}

CONTACT_CHANNEL_OPTIONS = [
    ("Telegram", "telegram"),
    ("WhatsApp", "whatsapp"),
    ("Телефон", "phone"),
    ("Email", "email"),
]
CONTACT_CHANNEL_BY_TOKEN = {token: label for label, token in CONTACT_CHANNEL_OPTIONS}
CONTACT_CHANNEL_ALIASES = {
    "telegram": "Telegram",
    "тг": "Telegram",
    "tg": "Telegram",
    "whatsapp": "WhatsApp",
    "ватсап": "WhatsApp",
    "вацап": "WhatsApp",
    "телефон": "Телефон",
    "phone": "Телефон",
    "звонок": "Телефон",
    "email": "Email",
    "e mail": "Email",
    "e-mail": "Email",
    "почта": "Email",
}

TARGET_UNKNOWN_PHRASES = {
    "пока выбираю",
    "нужна помощь с выбором",
    "ещё выбираю",
    "еще выбираю",
    "help",
    "помогите выбрать",
}

SUPPORTED_UPLOAD_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
SUPPORTED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(slots=True)
class Settings:
    bot_token: str
    db_path: Path
    manager_chat_id: int | None
    lead_webhook_url: str | None
    admin_ids: set[int]
    entry_source: str
    utm_source: str
    utm_campaign: str
    response_eta: str


def load_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    db_path = Path(os.getenv("DB_PATH", "data/leads.sqlite3")).expanduser()
    manager_chat_id_raw = os.getenv("MANAGER_CHAT_ID", "").strip()
    manager_chat_id = int(manager_chat_id_raw) if manager_chat_id_raw else None

    admin_ids_raw = os.getenv("ADMIN_IDS", "").strip()
    admin_ids: set[int] = set()
    if admin_ids_raw:
        for part in admin_ids_raw.split(","):
            part = part.strip()
            if part:
                admin_ids.add(int(part))

    return Settings(
        bot_token=bot_token,
        db_path=db_path,
        manager_chat_id=manager_chat_id,
        lead_webhook_url=os.getenv("LEAD_WEBHOOK_URL", "").strip() or None,
        admin_ids=admin_ids,
        entry_source=os.getenv("ENTRY_SOURCE", "video_01").strip() or "video_01",
        utm_source=os.getenv("UTM_SOURCE", "youtube").strip() or "youtube",
        utm_campaign=os.getenv("UTM_CAMPAIGN", "migration_video_a").strip() or "migration_video_a",
        response_eta=os.getenv("RESPONSE_ETA", "в течение 15 минут").strip() or "в течение 15 минут",
    )


class LeadStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    lead_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    entry_source TEXT,
                    utm_source TEXT,
                    utm_campaign TEXT,
                    telegram_user_id INTEGER NOT NULL,
                    telegram_username TEXT,
                    current_step TEXT NOT NULL DEFAULT 'service',
                    status TEXT NOT NULL DEFAULT 'active',
                    service TEXT,
                    departure_country TEXT,
                    departure_city TEXT,
                    timeline TEXT,
                    documents TEXT,
                    purpose TEXT,
                    main_contact TEXT,
                    additional_contact TEXT,
                    manager_notified INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_user_step ON leads (telegram_user_id, current_step, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_status ON leads (status, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_leads_created ON leads (created_at DESC)"
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["manager_notified"] = bool(item["manager_notified"])
        return item

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def create_lead(
        self,
        *,
        telegram_user_id: int,
        telegram_username: str | None,
        entry_source: str,
        utm_source: str,
        utm_campaign: str,
    ) -> dict[str, Any]:
        lead_id = uuid4().hex
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO leads (
                    lead_id, created_at, updated_at, completed_at,
                    entry_source, utm_source, utm_campaign,
                    telegram_user_id, telegram_username,
                    current_step, status, service, departure_country, departure_city,
                    timeline, documents, purpose, main_contact, additional_contact, manager_notified
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, 'service', 'active', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, 0)
                """,
                (
                    lead_id,
                    now,
                    now,
                    entry_source,
                    utm_source,
                    utm_campaign,
                    telegram_user_id,
                    telegram_username,
                ),
            )
        return self.get_lead(lead_id)  # type: ignore[return-value]

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
            return self._row_to_dict(row)

    def get_active_lead(self, telegram_user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM leads
                WHERE telegram_user_id = ?
                  AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (telegram_user_id,),
            ).fetchone()
            return self._row_to_dict(row)

    def update_lead(self, lead_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_lead(lead_id)
        mapped: dict[str, Any] = {}
        for key, value in fields.items():
            if key == "manager_notified":
                mapped[key] = int(bool(value))
            else:
                mapped[key] = value
        mapped["updated_at"] = self._now()
        assignments = ", ".join(f"{column} = ?" for column in mapped)
        values = list(mapped.values()) + [lead_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE leads SET {assignments} WHERE lead_id = ?", values)
        return self.get_lead(lead_id)

    def list_leads(self, *, status: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [self._row_to_dict(row) for row in rows if row is not None]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", value).replace("ё", "е").casefold().strip()
    text = re.sub(r"[^\w@+]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_options_map(options: list[tuple[str, str]]) -> dict[str, str]:
    return {normalize_text(label): label for label, _ in options}


SERVICE_BY_TEXT = build_options_map(SERVICE_OPTIONS)
COUNTRY_BY_TEXT = build_options_map(COUNTRY_OPTIONS)
TIMELINE_BY_TEXT = build_options_map(TIMELINE_OPTIONS)
DOCS_BY_TEXT = build_options_map(DOCS_OPTIONS)
PURPOSE_BY_TEXT = build_options_map(PURPOSE_OPTIONS)
NAV_BY_TEXT = {
    normalize_text(NAV_BACK): NAV_BACK,
    normalize_text(NAV_MENU): NAV_MENU,
    normalize_text(NAV_NEW): NAV_NEW,
    normalize_text(NAV_SKIP): NAV_SKIP,
    normalize_text(CONFIRM_TEXT): CONFIRM_TEXT,
    normalize_text(EDIT_TEXT): EDIT_TEXT,
    normalize_text(SHARE_CONTACT_TEXT): SHARE_CONTACT_TEXT,
}


FIELD_SEQUENCE = [
    (STEP_SERVICE, "service"),
    (STEP_COUNTRY, "departure_country"),
    (STEP_CITY, "departure_city"),
    (STEP_TIMELINE, "timeline"),
    (STEP_DOCS, "documents"),
    (STEP_PURPOSE, "purpose"),
    (STEP_MAIN_CONTACT, "main_contact"),
    (STEP_ADDITIONAL_CONTACT, "additional_contact"),
]
STEP_INDEX = {step: index for index, step in enumerate(STEP_SEQUENCE)}
STEP_PREVIOUS = {step: STEP_SEQUENCE[max(0, index - 1)] for index, step in enumerate(STEP_SEQUENCE)}
COUNTRY_TOKEN_BY_LABEL = {label: token for label, token in COUNTRY_OPTIONS}
CITY_BY_TEXT = {country_token: build_options_map(options) for country_token, options in CITY_OPTIONS_BY_COUNTRY.items()}
CITY_OPTIONS_BY_LABEL = {country_label: CITY_OPTIONS_BY_COUNTRY[token] for country_label, token in COUNTRY_TOKEN_BY_LABEL.items()}


def fields_from_step(step: str) -> list[str]:
    index = STEP_INDEX.get(step)
    if index is None:
        return []
    return [field for flow_step, field in FIELD_SEQUENCE[index:] if flow_step in STEP_TO_FIELD]


def option_label(text: str | None, options: list[tuple[str, str]]) -> str | None:
    return build_options_map(options).get(normalize_text(text))


def choose_goal(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in GOAL_ALIASES:
        return GOAL_ALIASES[norm]
    return build_options_map(GOAL_OPTIONS).get(norm)


def choose_timeline(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in TIMELINE_ALIASES:
        return TIMELINE_ALIASES[norm]
    return build_options_map(TIMELINE_COMPAT_OPTIONS).get(norm)


def choose_budget(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in BUDGET_ALIASES:
        return BUDGET_ALIASES[norm]
    return build_options_map(BUDGET_OPTIONS).get(norm)


def choose_contact_channel(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in CONTACT_CHANNEL_ALIASES:
        return CONTACT_CHANNEL_ALIASES[norm]
    return build_options_map(CONTACT_CHANNEL_OPTIONS).get(norm)


def parse_start_payload(payload: str | None, defaults: dict[str, str]) -> dict[str, str]:
    result = defaults.copy()
    raw = (payload or "").strip()
    if not raw:
        return result
    if "=" in raw:
        parsed = urllib.parse.parse_qs(raw.replace(" ", "&"), keep_blank_values=True)
        for source_key, target_key in (
            ("entry_source", "entry_source"),
            ("source", "entry_source"),
            ("utm_source", "utm_source"),
            ("utm_campaign", "utm_campaign"),
        ):
            values = parsed.get(source_key)
            if values and values[0].strip():
                result[target_key] = values[0].strip()
        return result
    parts = [part.strip() for part in re.split(r"[|,\s]+", raw) if part.strip()]
    if not parts:
        return result
    if len(parts) >= 1:
        result["entry_source"] = parts[0]
    if len(parts) >= 2:
        result["utm_source"] = parts[1]
    if len(parts) >= 3:
        result["utm_campaign"] = parts[2]
    return result


def classify_lead(lead: dict[str, Any]) -> str:
    if lead.get("consent") is False:
        return "stopped"

    goal = lead.get("goal")
    concrete_goal = bool(goal) and normalize_text(str(goal)) != normalize_text("Другое")
    target_known = bool(lead.get("target_country")) and not bool(lead.get("target_country_unknown"))
    timeline_known = bool(lead.get("timeline")) and normalize_text(str(lead.get("timeline"))) != normalize_text("Пока изучаю варианты")
    budget_known = bool(lead.get("budget")) and normalize_text(str(lead.get("budget"))) != normalize_text("Пока не знаю")
    contact_known = bool(lead.get("contact_value"))

    if concrete_goal and target_known and timeline_known and budget_known and contact_known:
        return "hot"
    if concrete_goal and contact_known:
        return "warm"
    return "cold"


def valid_contact_value(channel: str | None, value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if channel == "Email":
        return text if EMAIL_RE.fullmatch(text) else None
    digit_count = sum(ch.isdigit() for ch in text)
    if channel == "Телефон":
        return text if digit_count >= 7 else None
    if channel in {"Telegram", "WhatsApp"}:
        if text.startswith("@") or digit_count >= 7 or text.startswith("+"):
            return text
        return None
    return text


def is_supported_upload(file_name: str | None, mime_type: str | None) -> bool:
    if mime_type and mime_type.lower() in SUPPORTED_UPLOAD_MIME_TYPES:
        return True
    if file_name:
        suffix = Path(file_name).suffix.lower()
        if suffix in SUPPORTED_UPLOAD_EXTENSIONS:
            return True
    return False


def format_phone_number(phone_number: str) -> str:
    text = re.sub(r"\s+", "", phone_number.strip())
    if not text:
        return text
    if text.startswith("00"):
        return "+" + text[2:]
    if not text.startswith("+"):
        return "+" + text
    return text


def sanitize_additional_contact(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = text.strip()
    return cleaned or None


def display(value: Any, fallback: str = "—") -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def fields_for_clear_from(step: str) -> dict[str, None]:
    return {field: None for field in fields_from_step(step)}


def build_summary_text(lead: dict[str, Any]) -> str:
    return "\n".join(
        [
            "✅ Проверьте заявку:",
            f"Услуга: {display(lead.get('service'))}",
            f"Страна выезда: {display(lead.get('departure_country'))}",
            f"Город / регион: {display(lead.get('departure_city'))}",
            f"Срок поездки: {display(lead.get('timeline'))}",
            f"Документы: {display(lead.get('documents'))}",
            f"Цель въезда: {display(lead.get('purpose'))}",
            f"Основной контакт: {display(lead.get('main_contact'))}",
            f"Дополнительный контакт: {display(lead.get('additional_contact'))}",
        ]
    )


async def post_json(url: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


async def notify_manager(
    *,
    bot: Bot,
    store: LeadStore,
    settings: Settings,
    lead: dict[str, Any],
    trigger: str,
    send_webhook: bool,
    force: bool = False,
) -> None:
    if not force and lead.get("manager_notified"):
        return

    summary = build_manager_card(lead)
    if settings.manager_chat_id is not None:
        try:
            await bot.send_message(chat_id=settings.manager_chat_id, text=summary)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send manager card: %s", exc)

    if send_webhook and settings.lead_webhook_url:
        payload = build_webhook_payload(lead)
        try:
            await asyncio.to_thread(post_json, settings.lead_webhook_url, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send webhook (%s): %s", trigger, exc)

    store.update_lead(lead["lead_id"], manager_notified=True)


def build_webhook_payload(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "lead_completed",
        "lead_id": lead["lead_id"],
        "status": lead["status"],
        "source": lead.get("entry_source"),
        "created_at": lead["created_at"],
        "data": {
            "service": lead.get("service"),
            "departure_country": lead.get("departure_country"),
            "departure_city": lead.get("departure_city"),
            "timeline": lead.get("timeline"),
            "documents": lead.get("documents"),
            "purpose": lead.get("purpose"),
            "main_contact": lead.get("main_contact"),
            "additional_contact": lead.get("additional_contact"),
        },
    }


def build_manager_card(lead: dict[str, Any]) -> str:
    username = lead.get("telegram_username") or display(lead.get("telegram_user_id"))
    return "\n".join(
        [
            "Новая заявка",
            f"Статус: {display(lead.get('status'))}",
            f"Пользователь: {username}",
            f"Источник: {display(lead.get('entry_source'))}",
            f"Услуга: {display(lead.get('service'))}",
            f"Страна выезда: {display(lead.get('departure_country'))}",
            f"Город / регион: {display(lead.get('departure_city'))}",
            f"Срок поездки: {display(lead.get('timeline'))}",
            f"Документы: {display(lead.get('documents'))}",
            f"Цель въезда: {display(lead.get('purpose'))}",
            f"Основной контакт: {display(lead.get('main_contact'))}",
            f"Дополнительный контакт: {display(lead.get('additional_contact'))}",
        ]
    )


def service_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SERVICE_OPTIONS[0][0]), KeyboardButton(text=SERVICE_OPTIONS[1][0])],
            [KeyboardButton(text=SERVICE_OPTIONS[2][0]), KeyboardButton(text=SERVICE_OPTIONS[3][0])],
            [KeyboardButton(text=SERVICE_OPTIONS[4][0])],
            [KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def country_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=COUNTRY_OPTIONS[0][0]), KeyboardButton(text=COUNTRY_OPTIONS[1][0])],
            [KeyboardButton(text=COUNTRY_OPTIONS[2][0]), KeyboardButton(text=COUNTRY_OPTIONS[3][0])],
            [KeyboardButton(text=COUNTRY_OPTIONS[4][0])],
            [KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def city_keyboard(lead: dict[str, Any]) -> ReplyKeyboardMarkup:
    country_label = lead.get("departure_country")
    country_token = COUNTRY_TOKEN_BY_LABEL.get(country_label, "other")
    options = CITY_OPTIONS_BY_COUNTRY.get(country_token, CITY_OPTIONS_BY_COUNTRY["other"])
    rows = []
    row: list[KeyboardButton] = []
    for label, _token in options:
        row.append(KeyboardButton(text=label))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def timeline_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TIMELINE_OPTIONS[0][0]), KeyboardButton(text=TIMELINE_OPTIONS[1][0])],
            [KeyboardButton(text=TIMELINE_OPTIONS[2][0]), KeyboardButton(text=TIMELINE_OPTIONS[3][0])],
            [KeyboardButton(text=TIMELINE_OPTIONS[4][0])],
            [KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def docs_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=DOCS_OPTIONS[0][0]), KeyboardButton(text=DOCS_OPTIONS[1][0])],
            [KeyboardButton(text=DOCS_OPTIONS[2][0]), KeyboardButton(text=DOCS_OPTIONS[3][0])],
            [KeyboardButton(text=DOCS_OPTIONS[4][0])],
            [KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def purpose_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=PURPOSE_OPTIONS[0][0]), KeyboardButton(text=PURPOSE_OPTIONS[1][0])],
            [KeyboardButton(text=PURPOSE_OPTIONS[2][0]), KeyboardButton(text=PURPOSE_OPTIONS[3][0])],
            [KeyboardButton(text=PURPOSE_OPTIONS[4][0])],
            [KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SHARE_CONTACT_TEXT, request_contact=True)],
            [KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def additional_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=NAV_SKIP)],
            [KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CONFIRM_TEXT)],
            [KeyboardButton(text=EDIT_TEXT)],
            [KeyboardButton(text=NAV_BACK), KeyboardButton(text=NAV_MENU)],
        ],
        resize_keyboard=True,
    )


def done_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=NAV_MENU), KeyboardButton(text=NAV_NEW)]],
        resize_keyboard=True,
    )


def keyboard_for_step(lead: dict[str, Any]) -> ReplyKeyboardMarkup:
    step = lead.get("current_step")
    if step == STEP_SERVICE:
        return service_keyboard()
    if step == STEP_COUNTRY:
        return country_keyboard()
    if step == STEP_CITY:
        return city_keyboard(lead)
    if step == STEP_TIMELINE:
        return timeline_keyboard()
    if step == STEP_DOCS:
        return docs_keyboard()
    if step == STEP_PURPOSE:
        return purpose_keyboard()
    if step == STEP_MAIN_CONTACT:
        return contact_keyboard()
    if step == STEP_ADDITIONAL_CONTACT:
        return additional_contact_keyboard()
    if step == STEP_CONFIRM:
        return confirm_keyboard()
    if step == STEP_DONE:
        return done_keyboard()
    return service_keyboard()


def prompt_for_step(lead: dict[str, Any], settings: Settings) -> str:
    step = lead.get("current_step", STEP_SERVICE)
    if step == STEP_SERVICE:
        return "👋 Здравствуйте. Я помогу оформить заявку.\nВыберите, что вам нужно:"
    if step == STEP_COUNTRY:
        return "🌍 Из какой страны вы выезжаете?"
    if step == STEP_CITY:
        return "📍 Укажите город или регион выезда."
    if step == STEP_TIMELINE:
        return "⏱ Когда планируете поездку?"
    if step == STEP_DOCS:
        return "📄 Какие документы у вас уже есть?"
    if step == STEP_PURPOSE:
        return "🎯 Какая у вас цель въезда?"
    if step == STEP_MAIN_CONTACT:
        return "📞 Отправьте основной контакт для связи."
    if step == STEP_ADDITIONAL_CONTACT:
        return "💬 Укажите дополнительный контакт для связи.\nМожно написать номер, WhatsApp или Telegram-ник."
    if step == STEP_CONFIRM:
        return f"{build_summary_text(lead)}\n\nВсё верно?"
    if step == STEP_DONE:
        return "🙌 Спасибо. Заявка принята.\nМенеджер свяжется с вами в ближайшее время."
    return "Нажмите /start, чтобы начать."


async def send_current_prompt(message: Message, lead: dict[str, Any], settings: Settings) -> None:
    await message.answer(prompt_for_step(lead, settings), reply_markup=keyboard_for_step(lead))


async def transition_to_step(
    *,
    store: LeadStore,
    lead: dict[str, Any],
    next_step: str,
    updates: dict[str, Any] | None = None,
    clear_from_step: str | None = None,
    completed: bool = False,
    status: str | None = None,
) -> dict[str, Any]:
    payload = fields_for_clear_from(clear_from_step or next_step)
    if updates:
        payload.update(updates)
    payload["current_step"] = next_step
    if completed:
        payload["completed_at"] = now_iso()
    if status is not None:
        payload["status"] = status
    updated = store.update_lead(lead["lead_id"], **payload)
    if updated is None:
        raise RuntimeError("Lead not found")
    return updated


async def restart_current_flow(message: Message, store: LeadStore, settings: Settings, *, new_lead: bool = False) -> None:
    user = message.from_user
    if user is None:
        return

    active = store.get_active_lead(user.id)
    if new_lead and active is not None:
        store.update_lead(active["lead_id"], status=STEP_ABANDONED)
        active = None

    if active is None:
        payload = parse_start_payload(
            message.text.split(maxsplit=1)[1] if message.text and len(message.text.split(maxsplit=1)) > 1 else None,
            {
                "entry_source": settings.entry_source,
                "utm_source": settings.utm_source,
                "utm_campaign": settings.utm_campaign,
            },
        )
        lead = store.create_lead(
            telegram_user_id=user.id,
            telegram_username=f"@{user.username}" if user.username else None,
            entry_source=payload["entry_source"],
            utm_source=payload["utm_source"],
            utm_campaign=payload["utm_campaign"],
        )
    else:
        lead = await transition_to_step(
            store=store,
            lead=active,
            next_step=STEP_SERVICE,
            clear_from_step=STEP_SERVICE,
            status="active",
        )
    await send_current_prompt(message, lead, settings)


async def go_back(message: Message, store: LeadStore, settings: Settings, lead: dict[str, Any]) -> None:
    previous = STEP_PREVIOUS.get(lead.get("current_step"), STEP_SERVICE)
    updated = await transition_to_step(
        store=store,
        lead=lead,
        next_step=previous,
        clear_from_step=previous,
        status="active",
    )
    await send_current_prompt(message, updated, settings)


async def handle_choice_message(message: Message, store: LeadStore, settings: Settings, lead: dict[str, Any]) -> None:
    text = message.text or ""
    norm = normalize_text(text)

    if norm == normalize_text(NAV_MENU):
        await restart_current_flow(message, store, settings)
        return
    if norm == normalize_text(NAV_NEW):
        await restart_current_flow(message, store, settings, new_lead=True)
        return
    if norm == normalize_text(NAV_BACK):
        await go_back(message, store, settings, lead)
        return

    step = lead.get("current_step")
    if step == STEP_SERVICE:
        label = SERVICE_BY_TEXT.get(norm)
        if not label:
            await send_current_prompt(message, lead, settings)
            return
        updated = await transition_to_step(
            store=store,
            lead=lead,
            next_step=STEP_COUNTRY,
            updates={"service": label},
            clear_from_step=STEP_COUNTRY,
            status="active",
        )
        await send_current_prompt(message, updated, settings)
        return

    if step == STEP_COUNTRY:
        label = COUNTRY_BY_TEXT.get(norm)
        if not label:
            await send_current_prompt(message, lead, settings)
            return
        updated = await transition_to_step(
            store=store,
            lead=lead,
            next_step=STEP_CITY,
            updates={"departure_country": label},
            clear_from_step=STEP_CITY,
            status="active",
        )
        await send_current_prompt(message, updated, settings)
        return

    if step == STEP_CITY:
        country_token = COUNTRY_TOKEN_BY_LABEL.get(lead.get("departure_country"), "other")
        label = CITY_BY_TEXT.get(country_token, {}).get(norm)
        if not label:
            await send_current_prompt(message, lead, settings)
            return
        updated = await transition_to_step(
            store=store,
            lead=lead,
            next_step=STEP_TIMELINE,
            updates={"departure_city": label},
            clear_from_step=STEP_TIMELINE,
            status="active",
        )
        await send_current_prompt(message, updated, settings)
        return

    if step == STEP_TIMELINE:
        label = TIMELINE_BY_TEXT.get(norm)
        if not label:
            await send_current_prompt(message, lead, settings)
            return
        updated = await transition_to_step(
            store=store,
            lead=lead,
            next_step=STEP_DOCS,
            updates={"timeline": label},
            clear_from_step=STEP_DOCS,
            status="active",
        )
        await send_current_prompt(message, updated, settings)
        return

    if step == STEP_DOCS:
        label = DOCS_BY_TEXT.get(norm)
        if not label:
            await send_current_prompt(message, lead, settings)
            return
        updated = await transition_to_step(
            store=store,
            lead=lead,
            next_step=STEP_PURPOSE,
            updates={"documents": label},
            clear_from_step=STEP_PURPOSE,
            status="active",
        )
        await send_current_prompt(message, updated, settings)
        return

    if step == STEP_PURPOSE:
        label = PURPOSE_BY_TEXT.get(norm)
        if not label:
            await send_current_prompt(message, lead, settings)
            return
        updated = await transition_to_step(
            store=store,
            lead=lead,
            next_step=STEP_MAIN_CONTACT,
            updates={"purpose": label},
            clear_from_step=STEP_MAIN_CONTACT,
            status="active",
        )
        await send_current_prompt(message, updated, settings)
        return

    if step == STEP_ADDITIONAL_CONTACT:
        if norm == normalize_text(NAV_SKIP):
            updated = await transition_to_step(
                store=store,
                lead=lead,
                next_step=STEP_CONFIRM,
                updates={"additional_contact": None},
                clear_from_step=STEP_CONFIRM,
                status="active",
            )
            await send_current_prompt(message, updated, settings)
            return
        if norm == normalize_text(NAV_MENU):
            await restart_current_flow(message, store, settings)
            return
        if norm == normalize_text(NAV_BACK):
            await go_back(message, store, settings, lead)
            return
        additional_contact = sanitize_additional_contact(message.text)
        if not additional_contact:
            await send_current_prompt(message, lead, settings)
            return
        updated = await transition_to_step(
            store=store,
            lead=lead,
            next_step=STEP_CONFIRM,
            updates={"additional_contact": additional_contact},
            clear_from_step=STEP_CONFIRM,
            status="active",
        )
        await send_current_prompt(message, updated, settings)
        return

    if step == STEP_CONFIRM:
        if norm == normalize_text(CONFIRM_TEXT):
            updated = await transition_to_step(
                store=store,
                lead=lead,
                next_step=STEP_DONE,
                completed=True,
                status="completed",
            )
            await notify_manager(bot=message.bot, store=store, settings=settings, lead=updated, trigger="finalize", send_webhook=True, force=True)
            await send_current_prompt(message, updated, settings)
            return
        if norm == normalize_text(EDIT_TEXT):
            updated = await transition_to_step(
                store=store,
                lead=lead,
                next_step=STEP_SERVICE,
                clear_from_step=STEP_SERVICE,
                status="active",
            )
            await send_current_prompt(message, updated, settings)
            return
        if norm == normalize_text(NAV_BACK):
            await go_back(message, store, settings, lead)
            return
        if norm == normalize_text(NAV_MENU):
            await restart_current_flow(message, store, settings)
            return
        await send_current_prompt(message, lead, settings)
        return

    if step == STEP_DONE:
        if norm == normalize_text(NAV_MENU):
            await restart_current_flow(message, store, settings)
            return
        if norm == normalize_text(NAV_NEW):
            await restart_current_flow(message, store, settings, new_lead=True)
            return
        await send_current_prompt(message, lead, settings)
        return

    await send_current_prompt(message, lead, settings)


async def handle_main_contact(message: Message, store: LeadStore, settings: Settings, lead: dict[str, Any]) -> None:
    if lead.get("current_step") != STEP_MAIN_CONTACT:
        await handle_choice_message(message, store, settings, lead)
        return

    if message.contact is None:
        await handle_choice_message(message, store, settings, lead)
        return

    contact = message.contact
    main_contact = format_phone_number(contact.phone_number)
    updated = await transition_to_step(
        store=store,
        lead=lead,
        next_step=STEP_ADDITIONAL_CONTACT,
        updates={"main_contact": main_contact},
        clear_from_step=STEP_ADDITIONAL_CONTACT,
        status="active",
    )
    await send_current_prompt(message, updated, settings)


async def handle_text(message: Message, store: LeadStore, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return

    if message.text is None:
        return

    if message.text.startswith("/start"):
        active = store.get_active_lead(user.id)
        if active is None:
            await restart_current_flow(message, store, settings)
            return
        await send_current_prompt(message, active, settings)
        return

    active = store.get_active_lead(user.id)
    if active is None:
        await message.answer("Нажмите /start, чтобы начать.")
        return

    await handle_choice_message(message, store, settings, active)


def is_admin(user_id: int, settings: Settings) -> bool:
    return not settings.admin_ids or user_id in settings.admin_ids


async def handle_admin_leads(message: Message, store: LeadStore, settings: Settings, status: str | None = None) -> None:
    user = message.from_user
    if user is None:
        return
    if not is_admin(user.id, settings):
        await message.answer("Недостаточно прав.")
        return
    leads = store.list_leads(status=status, limit=10)
    if not leads:
        await message.answer("Заявок пока нет.")
        return
    lines = []
    for lead in leads:
        lines.append(f"{lead['lead_id']} | {display(lead.get('status'))} | {display(lead.get('service'))} | {display(lead.get('main_contact'))} | {display(lead.get('created_at'))}")
    await message.answer("\n".join(lines))


async def handle_admin_lead(message: Message, store: LeadStore, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return
    if not is_admin(user.id, settings):
        await message.answer("Недостаточно прав.")
        return
    args = message.text.split(maxsplit=1)[1].strip() if message.text and len(message.text.split(maxsplit=1)) > 1 else ""
    if not args:
        await message.answer("Использование: /lead <id>")
        return
    lead = store.get_lead(args)
    if lead is None:
        await message.answer("Заявка не найдена.")
        return
    await message.answer(build_manager_card(lead))


async def handle_admin_done(message: Message, store: LeadStore, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return
    if not is_admin(user.id, settings):
        await message.answer("Недостаточно прав.")
        return
    args = message.text.split(maxsplit=1)[1].strip() if message.text and len(message.text.split(maxsplit=1)) > 1 else ""
    if not args:
        await message.answer("Использование: /done <id>")
        return
    lead = store.get_lead(args)
    if lead is None:
        await message.answer("Заявка не найдена.")
        return
    store.update_lead(args, status="done", completed_at=now_iso())
    await message.answer("Заявка отмечена как обработанная.")


async def handle_manager_command(message: Message, store: LeadStore, settings: Settings, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return
    active = store.get_active_lead(user.id)
    if active is None:
        await message.answer("Сначала пройдите заявку через /start.")
        return
    updated = store.update_lead(active["lead_id"], status="completed", current_step=STEP_DONE, completed_at=now_iso())
    if updated is None:
        return
    await notify_manager(bot=bot, store=store, settings=settings, lead=updated, trigger="manual", send_webhook=True, force=True)
    await message.answer("Заявка отправлена менеджеру.")


async def run() -> None:
    settings = load_settings()
    store = LeadStore(settings.db_path)
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    router = Router()

    @router.message(Command("start"))
    async def on_start(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        active = store.get_active_lead(user.id)
        if active is None:
            payload = parse_start_payload(
                message.text.split(maxsplit=1)[1] if message.text and len(message.text.split(maxsplit=1)) > 1 else None,
                {
                    "entry_source": settings.entry_source,
                    "utm_source": settings.utm_source,
                    "utm_campaign": settings.utm_campaign,
                },
            )
            lead = store.create_lead(
                telegram_user_id=user.id,
                telegram_username=f"@{user.username}" if user.username else None,
                entry_source=payload["entry_source"],
                utm_source=payload["utm_source"],
                utm_campaign=payload["utm_campaign"],
            )
        else:
            lead = active
        await send_current_prompt(message, lead, settings)

    @router.message(Command("manager"))
    async def on_manager(message: Message) -> None:
        await handle_manager_command(message, store, settings, bot)

    @router.message(Command("leads"))
    async def on_leads(message: Message) -> None:
        await handle_admin_leads(message, store, settings)

    @router.message(Command("hot"))
    async def on_hot(message: Message) -> None:
        await handle_admin_leads(message, store, settings, status="active")

    @router.message(Command("cold"))
    async def on_cold(message: Message) -> None:
        await handle_admin_leads(message, store, settings, status="done")

    @router.message(Command("lead"))
    async def on_lead(message: Message) -> None:
        await handle_admin_lead(message, store, settings)

    @router.message(Command("done"))
    async def on_done(message: Message) -> None:
        await handle_admin_done(message, store, settings)

    @router.message(F.contact)
    async def on_contact(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        active = store.get_active_lead(user.id)
        if active is None:
            await message.answer("Нажмите /start, чтобы начать.")
            return
        await handle_main_contact(message, store, settings, active)

    @router.message()
    async def on_text(message: Message) -> None:
        await handle_text(message, store, settings)

    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
