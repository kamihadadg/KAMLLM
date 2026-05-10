"""App database: users and projects (NotebookLM-style workspaces)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def data_dir() -> Path:
    raw = os.getenv("KAMLLM_DATA_DIR", "data")
    p = Path(raw)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def app_database_path() -> Path:
    return data_dir() / "kamllm.sqlite"


def project_index_dir(public_id: str) -> Path:
    d = data_dir() / "projects" / public_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def connect() -> sqlite3.Connection:
    app_database_path().parent.mkdir(parents=True, exist_ok=True)
    cx = sqlite3.connect(str(app_database_path()))
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA foreign_keys = ON")
    return cx


def init_db() -> None:
    with connect() as cx:
        cx.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                public_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
            """
        )
        cx.commit()
