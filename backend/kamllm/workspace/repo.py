from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from shutil import rmtree
from typing import Any

import bcrypt
import jwt

from kamllm.workspace.db import connect, data_dir, project_index_dir


JWT_SECRET = os.getenv("JWT_SECRET", "dev-change-me-set-JWT_SECRET-in-env")
JWT_ALG = "HS256"
JWT_EXP_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))


@dataclass
class User:
    id: int
    email: str


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, stored_hash_ascii: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), stored_hash_ascii.encode("ascii"))


def register_user(email: str, password: str) -> User:
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    em = email.strip().lower()
    h = _hash_pw(password)
    try:
        with connect() as cx:
            cur = cx.execute(
                "INSERT INTO users (email, password_hash) VALUES (?, ?)",
                (em, h),
            )
            uid = int(cur.lastrowid)
            cx.commit()
    except sqlite3.IntegrityError as exc:
        raise ValueError("Email already registered") from exc
    return User(id=uid, email=em)


def authenticate(email: str, password: str) -> User | None:
    em = email.strip().lower()
    with connect() as cx:
        row = cx.execute(
            "SELECT id, password_hash FROM users WHERE email = ? COLLATE NOCASE",
            (em,),
        ).fetchone()
    if row is None:
        return None
    if not verify_password(password, str(row["password_hash"])):
        return None
    return User(id=int(row["id"]), email=em)


def issue_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "exp": now + timedelta(days=JWT_EXP_DAYS),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> tuple[int, str]:
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    return int(payload["sub"]), str(payload["email"])


def create_project(user_id: int, title: str) -> dict[str, Any]:
    public_id = str(uuid.uuid4())
    _ = project_index_dir(public_id)
    t = title.strip() or "Untitled project"
    with connect() as cx:
        cx.execute(
            "INSERT INTO projects (user_id, public_id, title) VALUES (?, ?, ?)",
            (user_id, public_id, t),
        )
        cx.commit()
    return {"public_id": public_id, "title": t}


def list_projects(user_id: int) -> list[dict[str, Any]]:
    with connect() as cx:
        rows = cx.execute(
            "SELECT public_id, title, created_at, updated_at FROM projects WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_project_for_user(public_id: str, user_id: int) -> dict[str, Any] | None:
    with connect() as cx:
        row = cx.execute(
            "SELECT id, public_id, title, user_id FROM projects WHERE public_id = ?",
            (public_id,),
        ).fetchone()
    if row is None or int(row["user_id"]) != user_id:
        return None
    return {"id": int(row["id"]), "public_id": row["public_id"], "title": row["title"]}


def delete_project_completely(public_id: str, user_id: int) -> bool:
    with connect() as cx:
        row = cx.execute(
            "SELECT user_id FROM projects WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if row is None or int(row["user_id"]) != user_id:
            return False
        cx.execute("DELETE FROM projects WHERE public_id = ?", (public_id,))
        cx.commit()
    idx = data_dir() / "projects" / public_id
    if idx.is_dir():
        rmtree(idx, ignore_errors=True)
    return True


def touch_project(public_id: str) -> None:
    with connect() as cx:
        cx.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE public_id = ?",
            (public_id,),
        )
        cx.commit()
