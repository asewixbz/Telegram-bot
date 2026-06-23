from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STEP_START = "start"
STEP_CONSENT = "consent"
STEP_GOAL = "goal"
STEP_CITIZENSHIP = "citizenship"
STEP_CURRENT_COUNTRY = "current_country"
STEP_TARGET_COUNTRY = "target_country"
STEP_TIMELINE = "timeline"
STEP_BUDGET = "budget"
STEP_CONTACT_CHANNEL = "contact_channel"
STEP_CONTACT_VALUE = "contact_value"
STEP_FINALIZE = "finalize"
STEP_FILE_UPLOAD = "file_upload"
STEP_END_NO_CONSENT = "end_no_consent"
STEP_DONE = "done"
STEP_ABANDONED = "abandoned"

STEP_LABELS = {
    STEP_START: "Старт",
    STEP_CONSENT: "Согласие",
    STEP_GOAL: "Цель",
    STEP_CITIZENSHIP: "Гражданство",
    STEP_CURRENT_COUNTRY: "Текущая страна",
    STEP_TARGET_COUNTRY: "Страна назначения",
    STEP_TIMELINE: "Сроки",
    STEP_BUDGET: "Бюджет",
    STEP_CONTACT_CHANNEL: "Канал связи",
    STEP_CONTACT_VALUE: "Контакт",
    STEP_FINALIZE: "Финал",
    STEP_FILE_UPLOAD: "Документы",
    STEP_END_NO_CONSENT: "Без согласия",
    STEP_DONE: "Завершено",
    STEP_ABANDONED: "Брошено",
}

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

TIMELINE_OPTIONS = [
    ("Срочно", "urgent"),
    ("1–3 месяца", "m1_3"),
    ("3–6 месяцев", "m3_6"),
    ("Пока изучаю варианты", "researching"),
]
TIMELINE_BY_TOKEN = {token: label for label, token in TIMELINE_OPTIONS}
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
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    entry_source TEXT,
                    utm_source TEXT,
                    utm_campaign TEXT,
                    telegram_user_id INTEGER NOT NULL,
                    telegram_username TEXT,
                    consent INTEGER,
                    goal TEXT,
                    citizenship TEXT,
                    current_country TEXT,
                    target_country TEXT,
                    target_country_unknown INTEGER NOT NULL DEFAULT 0,
                    timeline TEXT,
                    budget TEXT,
                    preferred_contact_channel TEXT,
                    contact_value TEXT,
                    status TEXT NOT NULL DEFAULT 'cold',
                    current_step TEXT NOT NULL DEFAULT 'start',
                    manager_notified INTEGER NOT NULL DEFAULT 0,
                    files_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    telegram_file_id TEXT NOT NULL,
                    file_name TEXT,
                    mime_type TEXT,
                    file_kind TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads (lead_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id TEXT NOT NULL,
                    author_id INTEGER NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads (lead_id)
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
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_files_lead ON lead_files (lead_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_notes_lead ON lead_notes (lead_id, created_at)"
            )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row | None, files: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        if row is None:
            return None
        item = dict(row)
        item["consent"] = None if item["consent"] is None else bool(item["consent"])
        item["target_country_unknown"] = bool(item["target_country_unknown"])
        item["manager_notified"] = bool(item["manager_notified"])
        item["files_count"] = int(item["files_count"] or 0)
        item["files"] = files or []
        return item

    def _now(self) -> str:
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
                    lead_id, created_at, started_at, updated_at, completed_at,
                    entry_source, utm_source, utm_campaign,
                    telegram_user_id, telegram_username,
                    consent, goal, citizenship, current_country,
                    target_country, target_country_unknown,
                    timeline, budget, preferred_contact_channel, contact_value,
                    status, current_step, manager_notified, files_count
                ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, 'cold', ?, 0, 0)
                """,
                (
                    lead_id,
                    now,
                    now,
                    now,
                    entry_source,
                    utm_source,
                    utm_campaign,
                    telegram_user_id,
                    telegram_username,
                    STEP_START,
                ),
            )
        return self.get_lead(lead_id, include_files=True)  # type: ignore[return-value]

    def get_lead(self, lead_id: str, include_files: bool = True) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
            files = self.get_files(lead_id) if include_files else []
            return self._row_to_dict(row, files)

    def get_active_lead(self, telegram_user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM leads
                WHERE telegram_user_id = ?
                  AND current_step NOT IN (?, ?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (telegram_user_id, STEP_DONE, STEP_END_NO_CONSENT, STEP_ABANDONED),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row, self.get_files(row["lead_id"]))

    def get_latest_lead(self, telegram_user_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM leads WHERE telegram_user_id = ? ORDER BY created_at DESC LIMIT 1",
                (telegram_user_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_dict(row, self.get_files(row["lead_id"]))

    def update_lead(self, lead_id: str, **fields: Any) -> dict[str, Any] | None:
        if not fields:
            return self.get_lead(lead_id)
        mapped: dict[str, Any] = {}
        for key, value in fields.items():
            if key in {"consent", "target_country_unknown", "manager_notified"}:
                if value is None:
                    mapped[key] = None
                else:
                    mapped[key] = int(bool(value))
            else:
                mapped[key] = value
        mapped["updated_at"] = self._now()
        assignments = ", ".join(f"{column} = ?" for column in mapped)
        values = list(mapped.values()) + [lead_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE leads SET {assignments} WHERE lead_id = ?", values)
        return self.get_lead(lead_id)

    def set_status(self, lead_id: str, status: str) -> dict[str, Any] | None:
        return self.update_lead(lead_id, status=status)

    def mark_abandoned(self, lead_id: str) -> dict[str, Any] | None:
        return self.update_lead(lead_id, current_step=STEP_ABANDONED, status="abandoned")

    def mark_done(self, lead_id: str) -> dict[str, Any] | None:
        completed_at = self._now()
        return self.update_lead(lead_id, current_step=STEP_DONE, completed_at=completed_at)

    def mark_no_consent(self, lead_id: str) -> dict[str, Any] | None:
        completed_at = self._now()
        return self.update_lead(lead_id, current_step=STEP_END_NO_CONSENT, completed_at=completed_at, status="stopped")

    def mark_manager_notified(self, lead_id: str) -> dict[str, Any] | None:
        return self.update_lead(lead_id, manager_notified=True)

    def add_note(self, lead_id: str, author_id: int, note: str) -> None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO lead_notes (lead_id, author_id, note, created_at) VALUES (?, ?, ?, ?)",
                (lead_id, author_id, note, now),
            )

    def get_notes(self, lead_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, author_id, note, created_at FROM lead_notes WHERE lead_id = ? ORDER BY created_at ASC",
                (lead_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_file(
        self,
        lead_id: str,
        telegram_file_id: str,
        file_name: str | None,
        mime_type: str | None,
        file_kind: str,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lead_files (lead_id, telegram_file_id, file_name, mime_type, file_kind, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (lead_id, telegram_file_id, file_name, mime_type, file_kind, now),
            )
            conn.execute(
                "UPDATE leads SET files_count = files_count + 1, updated_at = ? WHERE lead_id = ?",
                (now, lead_id),
            )
        return self.get_lead(lead_id)

    def get_files(self, lead_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, telegram_file_id, file_name, mime_type, file_kind, created_at
                FROM lead_files
                WHERE lead_id = ?
                ORDER BY created_at ASC
                """,
                (lead_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_leads(self, *, status: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM leads WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [self._row_to_dict(row, self.get_files(row["lead_id"])) for row in rows if row is not None]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", value).replace("ё", "е").casefold().strip()
    text = re.sub(r"[^\w@+]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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


def choose_goal(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in GOAL_ALIASES:
        return GOAL_ALIASES[norm]
    for label, _token in GOAL_OPTIONS:
        if norm == normalize_text(label):
            return label
    return None


def choose_timeline(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in TIMELINE_ALIASES:
        return TIMELINE_ALIASES[norm]
    for label, _token in TIMELINE_OPTIONS:
        if norm == normalize_text(label):
            return label
    return None


def choose_budget(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in BUDGET_ALIASES:
        return BUDGET_ALIASES[norm]
    for label, _token in BUDGET_OPTIONS:
        if norm == normalize_text(label):
            return label
    return None


def choose_contact_channel(text: str | None) -> str | None:
    norm = normalize_text(text)
    if not norm:
        return None
    if norm in CONTACT_CHANNEL_ALIASES:
        return CONTACT_CHANNEL_ALIASES[norm]
    for label, _token in CONTACT_CHANNEL_OPTIONS:
        if norm == normalize_text(label):
            return label
    return None


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


def build_webhook_payload(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "lead_completed",
        "lead_id": lead["lead_id"],
        "status": lead["status"],
        "source": lead.get("entry_source"),
        "created_at": lead["created_at"],
        "data": {
            "goal": lead.get("goal"),
            "citizenship": lead.get("citizenship"),
            "current_country": lead.get("current_country"),
            "target_country": lead.get("target_country"),
            "target_country_unknown": lead.get("target_country_unknown"),
            "timeline": lead.get("timeline"),
            "budget": lead.get("budget"),
            "preferred_contact_channel": lead.get("preferred_contact_channel"),
            "contact_value": lead.get("contact_value"),
        },
    }


def display(value: Any, fallback: str = "—") -> str:
    if value in (None, ""):
        return fallback
    return str(value)


def consent_label(value: Any) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "pending"


def build_manager_card(lead: dict[str, Any]) -> str:
    target_country = lead.get("target_country")
    if lead.get("target_country_unknown") and not target_country:
        target_country = "Пока выбираю"
    return "\n".join(
        [
            "Новая заявка",
            f"Статус: {display(lead.get('status'))}",
            f"Цель: {display(lead.get('goal'))}",
            f"Гражданство: {display(lead.get('citizenship'))}",
            f"Сейчас в: {display(lead.get('current_country'))}",
            f"Страна цели: {display(target_country)}",
            f"Сроки: {display(lead.get('timeline'))}",
            f"Бюджет: {display(lead.get('budget'))}",
            f"Контакт: {display(lead.get('contact_value'))}",
            f"Канал: {display(lead.get('preferred_contact_channel'))}",
            f"Источник: {display(lead.get('entry_source'))}",
            f"Consent: {consent_label(lead.get('consent'))}",
        ]
    )


def build_webhook_lead_summary(lead: dict[str, Any]) -> dict[str, Any]:
    return {
        "goal": lead.get("goal"),
        "citizenship": lead.get("citizenship"),
        "current_country": lead.get("current_country"),
        "target_country": lead.get("target_country"),
        "target_country_unknown": lead.get("target_country_unknown"),
        "timeline": lead.get("timeline"),
        "budget": lead.get("budget"),
        "preferred_contact_channel": lead.get("preferred_contact_channel"),
        "contact_value": lead.get("contact_value"),
    }


def build_resume_text(lead: dict[str, Any]) -> str:
    step = lead.get("current_step", STEP_START)
    label = STEP_LABELS.get(step, step)
    if step in {STEP_FINALIZE, STEP_FILE_UPLOAD}:
        return (
            f"У вас уже есть незавершённая заявка. Последний шаг — «{label}». "
            f"Можно продолжить с этого места или начать заново."
        )
    return f"У вас уже есть незавершённая заявка. Текущий шаг — «{label}». Продолжить с этого места или начать заново?"


def option_keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows]
    )


def start_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Начать", "lead:start")],
            [("Задать вопрос менеджеру", "lead:manager")],
        ]
    )


def resume_keyboard(lead_id: str) -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Продолжить", f"lead:resume:{lead_id}")],
            [("Начать заново", f"lead:restart:{lead_id}")],
        ]
    )


def consent_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Согласен", "lead:consent:yes"), ("Не согласен", "lead:consent:no")],
        ]
    )


def goal_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("ВНЖ", "lead:goal:vnj"), ("ПМЖ", "lead:goal:pmzh")],
            [("Виза", "lead:goal:visa"), ("Гражданство", "lead:goal:citizenship")],
            [("Работа", "lead:goal:work"), ("Учёба", "lead:goal:study")],
            [("Семья / воссоединение", "lead:goal:family"), ("Другое", "lead:goal:other")],
        ]
    )


def target_country_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Пока выбираю", "lead:target:unknown"), ("Нужна помощь с выбором", "lead:target:help")],
        ]
    )


def timeline_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Срочно", "lead:timeline:urgent"), ("1–3 месяца", "lead:timeline:m1_3")],
            [("3–6 месяцев", "lead:timeline:m3_6"), ("Пока изучаю варианты", "lead:timeline:researching")],
        ]
    )


def budget_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("До 1 000 €", "lead:budget:under_1000"), ("1 000–3 000 €", "lead:budget:1000_3000")],
            [("3 000–7 000 €", "lead:budget:3000_7000"), ("7 000 €+", "lead:budget:7000_plus")],
            [("Пока не знаю", "lead:budget:unknown")],
        ]
    )


def contact_channel_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Telegram", "lead:contact:telegram"), ("WhatsApp", "lead:contact:whatsapp")],
            [("Телефон", "lead:contact:phone"), ("Email", "lead:contact:email")],
        ]
    )


def finalize_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Отправить документы", "lead:final:docs")],
            [("Связаться с менеджером", "lead:final:manager")],
        ]
    )


def upload_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Связаться с менеджером", "lead:manager")],
        ]
    )


def no_consent_keyboard() -> InlineKeyboardMarkup:
    return option_keyboard(
        [
            [("Закрыть", "lead:close")],
        ]
    )


def current_step_keyboard(step: str, lead_id: str | None = None) -> InlineKeyboardMarkup | None:
    if step == STEP_START:
        return start_keyboard()
    if step == STEP_CONSENT:
        return consent_keyboard()
    if step == STEP_GOAL:
        return goal_keyboard()
    if step == STEP_TARGET_COUNTRY:
        return target_country_keyboard()
    if step == STEP_TIMELINE:
        return timeline_keyboard()
    if step == STEP_BUDGET:
        return budget_keyboard()
    if step == STEP_CONTACT_CHANNEL:
        return contact_channel_keyboard()
    if step == STEP_FINALIZE:
        return finalize_keyboard()
    if step == STEP_FILE_UPLOAD:
        return upload_keyboard()
    if step == STEP_END_NO_CONSENT:
        return no_consent_keyboard()
    if step in {STEP_DONE, STEP_ABANDONED}:
        return None
    return None


def prompt_for_step(step: str, settings: Settings) -> str:
    if step == STEP_START:
        return (
            "Привет! Я помогу быстро понять ваш запрос по миграции и передам заявку специалисту. "
            "Это займёт 2–3 минуты."
        )
    if step == STEP_CONSENT:
        return "Перед началом подтвердите, что вы согласны на обработку данных для консультации."
    if step == STEP_GOAL:
        return "Что вам нужно в первую очередь?"
    if step == STEP_CITIZENSHIP:
        return "Укажите ваше гражданство."
    if step == STEP_CURRENT_COUNTRY:
        return "В какой стране вы сейчас живёте?"
    if step == STEP_TARGET_COUNTRY:
        return "В какую страну вы хотите переехать?"
    if step == STEP_TIMELINE:
        return "Когда планируете начать процесс?"
    if step == STEP_BUDGET:
        return "Какой бюджет на переезд и оформление вы рассматриваете?"
    if step == STEP_CONTACT_CHANNEL:
        return "Куда удобнее отправить ответ специалиста?"
    if step == STEP_CONTACT_VALUE:
        return "Напишите ваш контакт для связи."
    if step == STEP_FINALIZE:
        return (
            f"Спасибо! Я передал вашу заявку специалисту. Обычно с вами свяжутся в течение {settings.response_eta}. "
            "Если хотите, можете сразу отправить документы следующим сообщением."
        )
    if step == STEP_FILE_UPLOAD:
        return "Можете отправить документы одним или несколькими сообщениями. Поддерживаются PDF, JPG, PNG, DOC, DOCX."
    if step == STEP_END_NO_CONSENT:
        return "Понимаю. Без согласия я не смогу продолжить. Если передумаете — нажмите /start."
    if step == STEP_DONE:
        return "Сценарий завершён. Если хотите начать новую заявку, нажмите /start."
    return "Нажмите /start, чтобы начать."


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

    card = build_manager_card(lead)
    if settings.manager_chat_id is not None:
        try:
            await bot.send_message(chat_id=settings.manager_chat_id, text=card)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send manager card: %s", exc)

    if send_webhook and settings.lead_webhook_url:
        payload = {
            "event": "lead_completed",
            "lead_id": lead["lead_id"],
            "status": lead["status"],
            "source": lead.get("entry_source"),
            "created_at": lead["created_at"],
            "data": build_webhook_lead_summary(lead),
        }
        try:
            await asyncio.to_thread(post_json, settings.lead_webhook_url, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send webhook (%s): %s", trigger, exc)

    store.mark_manager_notified(lead["lead_id"])


def build_lead_detail(lead: dict[str, Any]) -> str:
    files = lead.get("files", []) or []
    notes = lead.get("notes", []) or []
    target_country = lead.get("target_country")
    if lead.get("target_country_unknown") and not target_country:
        target_country = "Пока выбираю"
    lines = [
        f"Lead: {lead['lead_id']}",
        f"Статус: {display(lead.get('status'))}",
        f"Шаг: {display(lead.get('current_step'))}",
        f"Consent: {consent_label(lead.get('consent'))}",
        f"Цель: {display(lead.get('goal'))}",
        f"Гражданство: {display(lead.get('citizenship'))}",
        f"Сейчас в: {display(lead.get('current_country'))}",
        f"Страна цели: {display(target_country)}", 
        f"Сроки: {display(lead.get('timeline'))}",
        f"Бюджет: {display(lead.get('budget'))}",
        f"Канал: {display(lead.get('preferred_contact_channel'))}",
        f"Контакт: {display(lead.get('contact_value'))}",
        f"Источник: {display(lead.get('entry_source'))}",
        f"UTM source: {display(lead.get('utm_source'))}",
        f"UTM campaign: {display(lead.get('utm_campaign'))}",
        f"Files: {len(files)}", 
        f"Notes: {len(notes)}",
    ]
    if notes:
        lines.append("\nКомментарии:")
        for note in notes[-5:]:
            lines.append(f"- {note['created_at']} | {note['author_id']}: {note['note']}")
    return "\n".join(lines)


def is_admin(user_id: int, settings: Settings) -> bool:
    return not settings.admin_ids or user_id in settings.admin_ids


def parse_command_args(message: Message) -> str:
    if not message.text:
        return ""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return ""
    return parts[1].strip()


def resolve_option_from_token(step: str, token: str) -> str | None:
    if step == STEP_GOAL:
        return GOAL_BY_TOKEN.get(token)
    if step == STEP_TIMELINE:
        return TIMELINE_BY_TOKEN.get(token)
    if step == STEP_BUDGET:
        return BUDGET_BY_TOKEN.get(token)
    if step == STEP_CONTACT_CHANNEL:
        return CONTACT_CHANNEL_BY_TOKEN.get(token)
    return None


def text_matches_manager(text: str) -> bool:
    norm = normalize_text(text)
    return norm in {"менеджер", "связаться с менеджером", "задать вопрос менеджеру", "менеджеру"}


async def handle_lead_resume(message: Message, store: LeadStore, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return
    active = store.get_active_lead(user.id)
    if active:
        await message.answer(build_resume_text(active), reply_markup=resume_keyboard(active["lead_id"]))
        return

    payload = parse_start_payload(parse_command_args(message), {
        "entry_source": settings.entry_source,
        "utm_source": settings.utm_source,
        "utm_campaign": settings.utm_campaign,
    })
    lead = store.create_lead(
        telegram_user_id=user.id,
        telegram_username=f"@{user.username}" if user.username else None,
        entry_source=payload["entry_source"],
        utm_source=payload["utm_source"],
        utm_campaign=payload["utm_campaign"],
    )
    await message.answer(prompt_for_step(STEP_START, settings), reply_markup=current_step_keyboard(STEP_START, lead["lead_id"]))


async def send_current_step_prompt(target: Message | CallbackQuery, lead: dict[str, Any], settings: Settings) -> None:
    text = prompt_for_step(lead["current_step"], settings)
    markup = current_step_keyboard(lead["current_step"], lead["lead_id"])
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup)
        return
    if target.message:
        await target.message.edit_text(text, reply_markup=markup)
    await target.answer()


async def create_fresh_lead_from(message: Message, store: LeadStore, settings: Settings, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    user = message.from_user
    if user is None:
        raise RuntimeError("Missing user")
    if previous is None:
        payload = parse_start_payload(parse_command_args(message), {
            "entry_source": settings.entry_source,
            "utm_source": settings.utm_source,
            "utm_campaign": settings.utm_campaign,
        })
    else:
        payload = {
            "entry_source": previous.get("entry_source") or settings.entry_source,
            "utm_source": previous.get("utm_source") or settings.utm_source,
            "utm_campaign": previous.get("utm_campaign") or settings.utm_campaign,
        }
    return store.create_lead(
        telegram_user_id=user.id,
        telegram_username=f"@{user.username}" if user.username else None,
        entry_source=payload["entry_source"],
        utm_source=payload["utm_source"],
        utm_campaign=payload["utm_campaign"],
    )


async def update_and_advance(
    *,
    store: LeadStore,
    lead_id: str,
    next_step: str,
    status_fields: dict[str, Any],
    completed: bool = False,
    status_override: str | None = None,
) -> dict[str, Any]:
    fields = dict(status_fields)
    fields["current_step"] = next_step
    if completed and not fields.get("completed_at"):
        fields["completed_at"] = now_iso()
    lead = store.update_lead(lead_id, **fields)
    if lead is None:
        raise RuntimeError("Lead not found")
    if status_override is not None:
        lead = store.update_lead(lead_id, status=status_override)
    else:
        lead = store.update_lead(lead_id, status=classify_lead(lead))
    return lead or {}


async def handle_option_step(
    *,
    message_or_callback: Message | CallbackQuery,
    lead: dict[str, Any],
    step: str,
    value: str,
    store: LeadStore,
    settings: Settings,
    bot: Bot,
) -> None:
    lead_id = lead["lead_id"]
    if step == STEP_CONSENT:
        if value == "yes":
            lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_GOAL, status_fields={"consent": True})
            await send_current_step_prompt(message_or_callback, lead, settings)
            return
        if value == "no":
            lead = await update_and_advance(
                store=store,
                lead_id=lead_id,
                next_step=STEP_END_NO_CONSENT,
                status_fields={"consent": False},
                completed=True,
                status_override="stopped",
            )
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(prompt_for_step(STEP_END_NO_CONSENT, settings), reply_markup=current_step_keyboard(STEP_END_NO_CONSENT, lead_id))
            else:
                await message_or_callback.message.edit_text(prompt_for_step(STEP_END_NO_CONSENT, settings), reply_markup=current_step_keyboard(STEP_END_NO_CONSENT, lead_id))
                await message_or_callback.answer()
            return

    if step == STEP_GOAL:
        label = resolve_option_from_token(STEP_GOAL, value) or choose_goal(value)
        if not label:
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(prompt_for_step(STEP_GOAL, settings), reply_markup=goal_keyboard())
            else:
                await message_or_callback.answer("Выберите один из вариантов.")
            return
        lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_CITIZENSHIP, status_fields={"goal": label})
        await send_current_step_prompt(message_or_callback, lead, settings)
        return

    if step == STEP_TARGET_COUNTRY:
        if value in {"unknown", "help"}:
            lead = await update_and_advance(
                store=store,
                lead_id=lead_id,
                next_step=STEP_TIMELINE,
                status_fields={"target_country": None, "target_country_unknown": True},
            )
            await send_current_step_prompt(message_or_callback, lead, settings)
            return

    if step == STEP_TIMELINE:
        label = resolve_option_from_token(STEP_TIMELINE, value) or choose_timeline(value)
        if not label:
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(prompt_for_step(STEP_TIMELINE, settings), reply_markup=timeline_keyboard())
            else:
                await message_or_callback.answer("Выберите один из вариантов.")
            return
        lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_BUDGET, status_fields={"timeline": label})
        await send_current_step_prompt(message_or_callback, lead, settings)
        return

    if step == STEP_BUDGET:
        label = resolve_option_from_token(STEP_BUDGET, value) or choose_budget(value)
        if not label:
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(prompt_for_step(STEP_BUDGET, settings), reply_markup=budget_keyboard())
            else:
                await message_or_callback.answer("Выберите один из вариантов.")
            return
        lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_CONTACT_CHANNEL, status_fields={"budget": label})
        await send_current_step_prompt(message_or_callback, lead, settings)
        return

    if step == STEP_CONTACT_CHANNEL:
        label = resolve_option_from_token(STEP_CONTACT_CHANNEL, value) or choose_contact_channel(value)
        if not label:
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer(prompt_for_step(STEP_CONTACT_CHANNEL, settings), reply_markup=contact_channel_keyboard())
            else:
                await message_or_callback.answer("Выберите один из вариантов.")
            return
        lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_CONTACT_VALUE, status_fields={"preferred_contact_channel": label})
        await send_current_step_prompt(message_or_callback, lead, settings)
        return

    if step == STEP_FINALIZE:
        if value == "docs":
            lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_FILE_UPLOAD, status_fields={})
            await send_current_step_prompt(message_or_callback, lead, settings)
            return
        if value == "manager":
            lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_DONE, status_fields={}, completed=True)
            await notify_manager(bot=bot, store=store, settings=settings, lead=lead, trigger="manual", send_webhook=False, force=True)
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer("Сейчас передам ваш вопрос менеджеру.")
            else:
                await message_or_callback.message.edit_text("Сейчас передам ваш вопрос менеджеру.")
                await message_or_callback.answer()
            return

    if step == STEP_END_NO_CONSENT and value == "close":
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer("Диалог завершён. Если передумаете, нажмите /start.")
        else:
            await message_or_callback.message.edit_text("Диалог завершён. Если передумаете, нажмите /start.")
            await message_or_callback.answer()
        return

    if step == STEP_START and value == "manager":
        lead = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_DONE, status_fields={}, completed=True)
        await notify_manager(bot=bot, store=store, settings=settings, lead=lead, trigger="manual", send_webhook=False, force=True)
        if isinstance(message_or_callback, Message):
            await message_or_callback.answer("Сейчас передам ваш вопрос менеджеру.")
        else:
            await message_or_callback.message.edit_text("Сейчас передам ваш вопрос менеджеру.")
            await message_or_callback.answer()
        return

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer("Выберите один из вариантов кнопкой.")
    else:
        await message_or_callback.answer("Выберите один из вариантов кнопкой.")


async def process_text_step(message: Message, lead: dict[str, Any], store: LeadStore, settings: Settings, bot: Bot) -> None:
    if message.text is None:
        return
    normalized = normalize_text(message.text)
    if not normalized:
        await message.answer("Пожалуйста, отправьте ответ текстом или выберите вариант кнопкой.")
        return

    if normalized in {"начать", "start", "поехали"}:
        await handle_lead_resume(message, store, settings)
        return
    if text_matches_manager(message.text):
        updated = await update_and_advance(store=store, lead_id=lead["lead_id"], next_step=STEP_DONE, status_fields={}, completed=True)
        await notify_manager(bot=bot, store=store, settings=settings, lead=updated, trigger="manual", send_webhook=False, force=True)
        await message.answer("Сейчас передам ваш вопрос менеджеру.")
        return

    step = lead["current_step"]
    lead_id = lead["lead_id"]

    if step == STEP_CONSENT:
        if normalized in {"согласен", "да", "yes", "ok", "okay"}:
            updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_GOAL, status_fields={"consent": True})
            await send_current_step_prompt(message, updated, settings)
            return
        if normalized in {"не согласен", "нет", "no"}:
            updated = await update_and_advance(
                store=store,
                lead_id=lead_id,
                next_step=STEP_END_NO_CONSENT,
                status_fields={"consent": False},
                completed=True,
                status_override="stopped",
            )
            await message.answer(prompt_for_step(STEP_END_NO_CONSENT, settings), reply_markup=current_step_keyboard(STEP_END_NO_CONSENT, lead_id))
            return
        await message.answer(prompt_for_step(STEP_CONSENT, settings), reply_markup=consent_keyboard())
        return

    if step == STEP_GOAL:
        label = choose_goal(message.text)
        if not label:
            await message.answer(prompt_for_step(STEP_GOAL, settings), reply_markup=goal_keyboard())
            return
        updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_CITIZENSHIP, status_fields={"goal": label})
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_CITIZENSHIP:
        text = (message.text or "").strip()
        if len(text) < 2:
            await message.answer(prompt_for_step(STEP_CITIZENSHIP, settings))
            return
        updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_CURRENT_COUNTRY, status_fields={"citizenship": text})
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_CURRENT_COUNTRY:
        text = (message.text or "").strip()
        if len(text) < 2:
            await message.answer(prompt_for_step(STEP_CURRENT_COUNTRY, settings))
            return
        updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_TARGET_COUNTRY, status_fields={"current_country": text})
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_TARGET_COUNTRY:
        text = (message.text or "").strip()
        if normalize_text(text) in TARGET_UNKNOWN_PHRASES:
            updated = await update_and_advance(
                store=store,
                lead_id=lead_id,
                next_step=STEP_TIMELINE,
                status_fields={"target_country": None, "target_country_unknown": True},
            )
            await send_current_step_prompt(message, updated, settings)
            return
        if len(text) < 2:
            await message.answer(prompt_for_step(STEP_TARGET_COUNTRY, settings), reply_markup=target_country_keyboard())
            return
        updated = await update_and_advance(
            store=store,
            lead_id=lead_id,
            next_step=STEP_TIMELINE,
            status_fields={"target_country": text, "target_country_unknown": False},
        )
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_TIMELINE:
        label = choose_timeline(message.text)
        if not label:
            await message.answer(prompt_for_step(STEP_TIMELINE, settings), reply_markup=timeline_keyboard())
            return
        updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_BUDGET, status_fields={"timeline": label})
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_BUDGET:
        label = choose_budget(message.text)
        if not label:
            await message.answer(prompt_for_step(STEP_BUDGET, settings), reply_markup=budget_keyboard())
            return
        updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_CONTACT_CHANNEL, status_fields={"budget": label})
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_CONTACT_CHANNEL:
        label = choose_contact_channel(message.text)
        if not label:
            await message.answer(prompt_for_step(STEP_CONTACT_CHANNEL, settings), reply_markup=contact_channel_keyboard())
            return
        updated = await update_and_advance(
            store=store,
            lead_id=lead_id,
            next_step=STEP_CONTACT_VALUE,
            status_fields={"preferred_contact_channel": label},
        )
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_CONTACT_VALUE:
        contact = valid_contact_value(lead.get("preferred_contact_channel"), message.text)
        if not contact:
            await message.answer(prompt_for_step(STEP_CONTACT_VALUE, settings))
            return
        updated = await update_and_advance(
            store=store,
            lead_id=lead_id,
            next_step=STEP_FINALIZE,
            status_fields={"contact_value": contact},
            completed=True,
        )
        updated = store.update_lead(lead_id, status=classify_lead(updated)) or updated
        await notify_manager(bot=bot, store=store, settings=settings, lead=updated, trigger="finalize", send_webhook=True, force=True)
        await send_current_step_prompt(message, updated, settings)
        return

    if step == STEP_FINALIZE:
        if normalize_text(message.text) in {"отправить документы", "документы", "отправить документ"}:
            updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_FILE_UPLOAD, status_fields={})
            await send_current_step_prompt(message, updated, settings)
            return
        if text_matches_manager(message.text):
            updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_DONE, status_fields={}, completed=True)
            await notify_manager(bot=bot, store=store, settings=settings, lead=updated, trigger="manual", send_webhook=False, force=True)
            await message.answer("Сейчас передам ваш вопрос менеджеру.")
            return
        await message.answer(prompt_for_step(STEP_FINALIZE, settings), reply_markup=finalize_keyboard())
        return

    if step == STEP_FILE_UPLOAD:
        if text_matches_manager(message.text):
            updated = await update_and_advance(store=store, lead_id=lead_id, next_step=STEP_DONE, status_fields={}, completed=True)
            await notify_manager(bot=bot, store=store, settings=settings, lead=updated, trigger="manual", send_webhook=False, force=True)
            await message.answer("Сейчас передам ваш вопрос менеджеру.")
            return
        await message.answer(prompt_for_step(STEP_FILE_UPLOAD, settings), reply_markup=upload_keyboard())
        return

    if step in {STEP_END_NO_CONSENT, STEP_DONE, STEP_ABANDONED}:
        await message.answer("Нажмите /start, чтобы начать новую заявку.")
        return

    await message.answer("Нажмите /start, чтобы начать.")


async def handle_upload(message: Message, lead: dict[str, Any], store: LeadStore, settings: Settings, bot: Bot) -> None:
    if lead["current_step"] not in {STEP_FINALIZE, STEP_FILE_UPLOAD}:
        await message.answer("Сначала завершите анкету, после этого можно будет отправить документы.")
        return

    file_kind = "document"
    file_name = None
    mime_type = None
    telegram_file_id = None

    if message.document:
        file_kind = "document"
        file_name = message.document.file_name
        mime_type = message.document.mime_type
        telegram_file_id = message.document.file_id
    elif message.photo:
        file_kind = "photo"
        photo = message.photo[-1]
        telegram_file_id = photo.file_id
        mime_type = "image/jpeg"
        file_name = f"photo_{telegram_file_id}.jpg"
    else:
        return

    if not is_supported_upload(file_name, mime_type):
        await message.answer("Поддерживаются только PDF, JPG, PNG, DOC и DOCX.")
        return

    updated = store.add_file(lead["lead_id"], telegram_file_id, file_name, mime_type, file_kind)
    if updated is None:
        await message.answer("Не удалось сохранить файл. Попробуйте ещё раз.")
        return
    if updated["current_step"] == STEP_FINALIZE:
        updated = store.update_lead(lead["lead_id"], current_step=STEP_FILE_UPLOAD) or updated

    await message.answer(
        f"Файл сохранён. Сейчас у заявки {updated['files_count']} файл(ов). Можно отправить ещё или написать /manager.",
        reply_markup=upload_keyboard(),
    )


async def handle_manager_command(message: Message, store: LeadStore, settings: Settings, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return
    lead = store.get_active_lead(user.id)
    if lead is None:
        lead = store.create_lead(
            telegram_user_id=user.id,
            telegram_username=f"@{user.username}" if user.username else None,
            entry_source=settings.entry_source,
            utm_source=settings.utm_source,
            utm_campaign=settings.utm_campaign,
        )
    lead = await update_and_advance(store=store, lead_id=lead["lead_id"], next_step=STEP_DONE, status_fields={}, completed=True)
    await notify_manager(bot=bot, store=store, settings=settings, lead=lead, trigger="manual", send_webhook=False, force=True)
    await message.answer("Сейчас передам ваш вопрос менеджеру.")


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
        lines.append(
            f"{lead['lead_id']} | {display(lead.get('status'))} | {display(lead.get('goal'))} | {display(lead.get('contact_value'))} | {display(lead.get('created_at'))}"
        )
    await message.answer("\n".join(lines))


async def handle_admin_lead(message: Message, store: LeadStore, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return
    if not is_admin(user.id, settings):
        await message.answer("Недостаточно прав.")
        return
    lead_id = parse_command_args(message)
    if not lead_id:
        await message.answer("Использование: /lead <id>")
        return
    lead = store.get_lead(lead_id)
    if lead is None:
        await message.answer("Заявка не найдена.")
        return
    lead["notes"] = store.get_notes(lead_id)
    await message.answer(build_lead_detail(lead))


async def handle_admin_note(message: Message, store: LeadStore, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return
    if not is_admin(user.id, settings):
        await message.answer("Недостаточно прав.")
        return
    args = parse_command_args(message)
    if not args:
        await message.answer("Использование: /note <id> текст")
        return
    parts = args.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /note <id> текст")
        return
    lead_id, note = parts[0].strip(), parts[1].strip()
    if not note:
        await message.answer("Введите текст комментария.")
        return
    if store.get_lead(lead_id) is None:
        await message.answer("Заявка не найдена.")
        return
    store.add_note(lead_id, user.id, note)
    await message.answer("Комментарий добавлен.")


async def handle_admin_done(message: Message, store: LeadStore, settings: Settings) -> None:
    user = message.from_user
    if user is None:
        return
    if not is_admin(user.id, settings):
        await message.answer("Недостаточно прав.")
        return
    lead_id = parse_command_args(message)
    if not lead_id:
        await message.answer("Использование: /done <id>")
        return
    if store.get_lead(lead_id) is None:
        await message.answer("Заявка не найдена.")
        return
    store.mark_done(lead_id)
    await message.answer("Заявка отмечена как обработанная.")


def create_router(store: LeadStore, settings: Settings, bot: Bot) -> Router:
    router = Router()

    @router.message(Command("start"))
    async def on_start(message: Message) -> None:
        await handle_lead_resume(message, store, settings)

    @router.message(Command("manager"))
    async def on_manager(message: Message) -> None:
        await handle_manager_command(message, store, settings, bot)

    @router.message(Command("leads"))
    async def on_leads(message: Message) -> None:
        await handle_admin_leads(message, store, settings)

    @router.message(Command("hot"))
    async def on_hot(message: Message) -> None:
        await handle_admin_leads(message, store, settings, status="hot")

    @router.message(Command("warm"))
    async def on_warm(message: Message) -> None:
        await handle_admin_leads(message, store, settings, status="warm")

    @router.message(Command("cold"))
    async def on_cold(message: Message) -> None:
        await handle_admin_leads(message, store, settings, status="cold")

    @router.message(Command("lead"))
    async def on_lead(message: Message) -> None:
        await handle_admin_lead(message, store, settings)

    @router.message(Command("note"))
    async def on_note(message: Message) -> None:
        await handle_admin_note(message, store, settings)

    @router.message(Command("done"))
    async def on_done(message: Message) -> None:
        await handle_admin_done(message, store, settings)

    @router.callback_query(F.data.startswith("lead:"))
    async def on_callback(callback: CallbackQuery) -> None:
        if callback.data is None:
            await callback.answer()
            return
        parts = callback.data.split(":")
        if len(parts) < 2:
            await callback.answer()
            return
        action = parts[1]
        user = callback.from_user
        if user is None:
            await callback.answer()
            return

        if action == "start":
            lead = store.get_active_lead(user.id)
            if lead is None:
                lead = store.create_lead(
                    telegram_user_id=user.id,
                    telegram_username=f"@{user.username}" if user.username else None,
                    entry_source=settings.entry_source,
                    utm_source=settings.utm_source,
                    utm_campaign=settings.utm_campaign,
                )
            lead = await update_and_advance(store=store, lead_id=lead["lead_id"], next_step=STEP_CONSENT, status_fields={})
            await send_current_step_prompt(callback, lead, settings)
            return

        if action == "manager":
            lead = store.get_active_lead(user.id)
            if lead is None:
                lead = store.create_lead(
                    telegram_user_id=user.id,
                    telegram_username=f"@{user.username}" if user.username else None,
                    entry_source=settings.entry_source,
                    utm_source=settings.utm_source,
                    utm_campaign=settings.utm_campaign,
                )
            lead = await update_and_advance(store=store, lead_id=lead["lead_id"], next_step=STEP_DONE, status_fields={}, completed=True)
            await notify_manager(bot=bot, store=store, settings=settings, lead=lead, trigger="manual", send_webhook=False, force=True)
            if callback.message:
                await callback.message.edit_text("Сейчас передам ваш вопрос менеджеру.")
            await callback.answer()
            return

        if action == "resume" and len(parts) >= 3:
            lead_id = parts[2]
            lead = store.get_lead(lead_id)
            if lead is None or lead["telegram_user_id"] != user.id:
                await callback.answer("Заявка не найдена")
                return
            await send_current_step_prompt(callback, lead, settings)
            return

        if action == "restart" and len(parts) >= 3:
            lead_id = parts[2]
            lead = store.get_lead(lead_id)
            if lead is None or lead["telegram_user_id"] != user.id:
                await callback.answer("Заявка не найдена")
                return
            store.mark_abandoned(lead_id)
            fresh = await create_fresh_lead_from(callback.message or message, store, settings, previous=lead)
            await send_current_step_prompt(callback, fresh, settings)
            return

        if action in {"consent", "goal", "target", "timeline", "budget", "contact", "final", "close"}:
            lead = store.get_active_lead(user.id)
            if lead is None:
                lead = store.create_lead(
                    telegram_user_id=user.id,
                    telegram_username=f"@{user.username}" if user.username else None,
                    entry_source=settings.entry_source,
                    utm_source=settings.utm_source,
                    utm_campaign=settings.utm_campaign,
                )
            value = parts[2] if len(parts) >= 3 else ""
            current_step = lead["current_step"]
            if action == "consent":
                current_step = STEP_CONSENT
            elif action == "goal":
                current_step = STEP_GOAL
            elif action == "target":
                current_step = STEP_TARGET_COUNTRY
            elif action == "timeline":
                current_step = STEP_TIMELINE
            elif action == "budget":
                current_step = STEP_BUDGET
            elif action == "contact":
                current_step = STEP_CONTACT_CHANNEL
            elif action == "final":
                current_step = STEP_FINALIZE
            elif action == "close":
                current_step = STEP_END_NO_CONSENT
            await handle_option_step(
                message_or_callback=callback,
                lead=lead,
                step=current_step,
                value=value,
                store=store,
                settings=settings,
                bot=bot,
            )
            return

        await callback.answer()

    @router.message(F.document | F.photo)
    async def on_file(message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        lead = store.get_active_lead(user.id)
        if lead is None:
            await message.answer("Сначала завершите анкету, после этого можно будет отправить документы.")
            return
        await handle_upload(message, lead, store, settings, bot)

    @router.message(F.text)
    async def on_text(message: Message) -> None:
        if message.text is None:
            return
        if message.text.startswith("/"):
            return
        user = message.from_user
        if user is None:
            return
        lead = store.get_active_lead(user.id)
        if lead is None:
            if normalize_text(message.text) in {"начать", "start", "поехали"}:
                await handle_lead_resume(message, store, settings)
            elif text_matches_manager(message.text):
                await handle_manager_command(message, store, settings, bot)
            else:
                await message.answer("Нажмите /start, чтобы начать анкету.")
            return
        await process_text_step(message, lead, store, settings, bot)

    return router


async def run() -> None:
    settings = load_settings()
    store = LeadStore(settings.db_path)
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(create_router(store, settings, bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run())
