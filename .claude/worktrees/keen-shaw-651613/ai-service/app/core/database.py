import sqlite3
import os
from pathlib import Path
from app.core.config import settings


def get_db_path() -> str:
    # Resolve relative to this file's location (ai-service/app/core/)
    base = Path(__file__).parent.parent.parent  # ai-service/
    raw = settings.sqlite_db_path
    if os.path.isabs(raw):
        return raw
    return str((base / raw).resolve())


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def fetch_all(query: str, params: tuple = ()) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_one(query: str, params: tuple = ()) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
