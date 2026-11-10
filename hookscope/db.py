"""SQLite storage. One small repository per entity, all returning plain dicts."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY, mode TEXT NOT NULL, source_url TEXT, platform TEXT, title TEXT, author TEXT,
    duration REAL, metrics TEXT, note TEXT, is_mine INTEGER DEFAULT 0, status TEXT NOT NULL,
    steps TEXT, error TEXT, report TEXT, created_at TEXT NOT NULL, kind TEXT DEFAULT 'video'
);
CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scripts (
    id TEXT PRIMARY KEY, analysis_id TEXT, idea TEXT, script TEXT, edited_text TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY, analysis_ids TEXT, data TEXT, done TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat (id TEXT PRIMARY KEY, role TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS analyses_created ON analyses (created_at DESC);
"""

JSON_COLUMNS = {"metrics", "steps", "report", "idea", "script", "analysis_ids", "data", "done"}
ANALYSIS_FIELDS = {"mode", "source_url", "platform", "title", "author", "duration", "metrics", "note",
                   "is_mine", "status", "steps", "error", "report", "kind"}
# Columns added after the first release, created on old databases at start-up.
MIGRATIONS = {"analyses": {"kind": "TEXT DEFAULT 'video'"}}

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.ensure_dirs()
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
        _migrate(_conn)
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in MIGRATIONS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, spec in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")
    conn.commit()


def reset_for_tests() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = None


def _encode(values: dict) -> dict:
    return {k: (json.dumps(v, ensure_ascii=False) if k in JSON_COLUMNS and v is not None else v) for k, v in values.items()}


def _decode(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    out = dict(row)
    for key in JSON_COLUMNS & out.keys():
        if out[key] is not None:
            out[key] = json.loads(out[key])
    return out


def _execute(sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
    with _lock:
        conn = connect()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur


def _query(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        return [_decode(r) for r in connect().execute(sql, params).fetchall()]


# Analyses ---------------------------------------------------------------

def create_analysis(fields: dict) -> dict:
    row = {"id": new_id(), "created_at": now_iso(), "status": "queued", **_encode(
        {k: v for k, v in fields.items() if k in ANALYSIS_FIELDS})}
    cols = ", ".join(row)
    _execute(f"INSERT INTO analyses ({cols}) VALUES ({', '.join(':' + c for c in row)})", row)
    return get_analysis(row["id"])


def update_analysis(analysis_id: str, changes: dict) -> dict | None:
    safe = _encode({k: v for k, v in changes.items() if k in ANALYSIS_FIELDS})
    if safe:
        sets = ", ".join(f"{k} = :{k}" for k in safe)
        _execute(f"UPDATE analyses SET {sets} WHERE id = :id", {**safe, "id": analysis_id})
    return get_analysis(analysis_id)


def get_analysis(analysis_id: str) -> dict | None:
    rows = _query("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    return rows[0] if rows else None


def list_analyses(search: str = "", limit: int = 500) -> list[dict]:
    if search:
        like = f"%{search.lower()}%"
        return _query(
            "SELECT * FROM analyses WHERE lower(coalesce(title,'') || ' ' || coalesce(author,'') || ' ' || "
            "coalesce(source_url,'') || ' ' || coalesce(report,'')) LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like, limit))
    return _query("SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,))


def analyses_with_status(*statuses: str) -> list[dict]:
    marks = ", ".join("?" for _ in statuses)
    return _query(f"SELECT * FROM analyses WHERE status IN ({marks}) ORDER BY created_at", statuses)


def delete_analysis(analysis_id: str) -> None:
    _execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))


# Profile ----------------------------------------------------------------

EMPTY_PROFILE = {"niche": "", "audience": "", "pillars": [], "tone": "", "goals": "", "voice_facts": [],
                 "strongest_formats": [], "signature_phrases": []}


def get_profile() -> dict:
    rows = _query("SELECT data FROM profile WHERE id = 1")
    return {**EMPTY_PROFILE, **(rows[0]["data"] if rows else {})}


def save_profile(data: dict) -> dict:
    merged = {**EMPTY_PROFILE, **{k: v for k, v in data.items() if k in EMPTY_PROFILE}}
    _execute("INSERT INTO profile (id, data) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET data = excluded.data",
             (json.dumps(merged, ensure_ascii=False),))
    return merged


# Scripts ----------------------------------------------------------------

def create_script(analysis_id: str | None, idea: dict, script: dict) -> dict:
    row = {"id": new_id(), "analysis_id": analysis_id, "idea": idea, "script": script, "edited_text": None,
           "created_at": now_iso()}
    _execute("INSERT INTO scripts VALUES (:id, :analysis_id, :idea, :script, :edited_text, :created_at)", _encode(row))
    return get_script(row["id"])


def get_script(script_id: str) -> dict | None:
    rows = _query("SELECT * FROM scripts WHERE id = ?", (script_id,))
    return rows[0] if rows else None


def list_scripts() -> list[dict]:
    return _query("SELECT * FROM scripts ORDER BY created_at DESC")


def update_script_text(script_id: str, text: str | None) -> dict | None:
    _execute("UPDATE scripts SET edited_text = ? WHERE id = ?", (text, script_id))
    return get_script(script_id)


def delete_script(script_id: str) -> None:
    _execute("DELETE FROM scripts WHERE id = ?", (script_id,))


# Plans ------------------------------------------------------------------

def create_plan(analysis_ids: list[str], data: dict) -> dict:
    row = {"id": new_id(), "analysis_ids": analysis_ids, "data": data, "done": [], "created_at": now_iso()}
    _execute("INSERT INTO plans VALUES (:id, :analysis_ids, :data, :done, :created_at)", _encode(row))
    return get_plan(row["id"])


def get_plan(plan_id: str) -> dict | None:
    rows = _query("SELECT * FROM plans WHERE id = ?", (plan_id,))
    return rows[0] if rows else None


def list_plans() -> list[dict]:
    return _query("SELECT * FROM plans ORDER BY created_at DESC")


def set_plan_done(plan_id: str, done: list[int]) -> dict | None:
    _execute("UPDATE plans SET done = ? WHERE id = ?", (json.dumps(sorted(set(done))), plan_id))
    return get_plan(plan_id)


def delete_plan(plan_id: str) -> None:
    _execute("DELETE FROM plans WHERE id = ?", (plan_id,))


# Chat -------------------------------------------------------------------

def add_chat(role: str, text: str) -> dict:
    row = {"id": new_id(), "role": role, "text": text, "created_at": now_iso()}
    _execute("INSERT INTO chat VALUES (:id, :role, :text, :created_at)", row)
    return row


def list_chat(limit: int = 200) -> list[dict]:
    rows = _query("SELECT * FROM chat ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
    return list(reversed(rows))


def clear_chat() -> None:
    _execute("DELETE FROM chat")
