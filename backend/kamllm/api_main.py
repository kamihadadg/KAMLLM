"""
REST API: NotebookLM-style workspaces (auth + per-project PDF indexes + chat).

Run from `backend/` directory (so `.env`, `data/`, and JWT work as expected):

    uvicorn kamllm.api_main:app --host 127.0.0.1 --port 8765
    python -m kamllm.api_main
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

from kamllm.config import Settings, get_settings, replace_chroma_path
from kamllm.diagnostics import run_health
from kamllm.llm.ollama import OllamaError
from kamllm.qa import answer_question
from kamllm.rag.ingest_pdf import ingest_pdf_path
from kamllm.workspace.db import init_db, project_index_dir
from kamllm.workspace.repo import (
    User,
    authenticate,
    create_project,
    decode_token,
    delete_project_completely,
    get_project_for_user,
    issue_token,
    list_projects,
    register_user,
    touch_project,
)

ALLOWED_ORIGINS = os.getenv(
    "KAMLLM_CORS_ORIGINS",
    "http://127.0.0.1:3000,http://localhost:3000",
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="KAMLLM API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _bearer_token(authorization: str | None = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return authorization[7:].strip()


def current_user(token: Annotated[str, Depends(_bearer_token)]) -> User:
    try:
        uid, email = decode_token(token)
    except jwt.exceptions.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired") from None
    except jwt.exceptions.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token") from None
    return User(id=uid, email=email)


def _settings_for_project(public_id: str) -> Settings:
    """RAG settings scoped to this project's index directory."""
    base = get_settings()
    return replace_chroma_path(base, project_index_dir(public_id))


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class ProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1)
    top_k: int | None = Field(None, ge=1, le=50)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str


@app.get("/api/health")
def health() -> dict:
    base = get_settings()
    report = run_health(base, include_index=False)
    llm_ok = report.ollama_ok and report.embed_ok and report.chat_ok
    return {
        "models_ready": llm_ok,
        "ollama": {"ok": report.ollama_ok, "error": report.ollama_error},
        "embed": {"ok": report.embed_ok, "dimension": report.embed_dim, "error": report.embed_error},
        "chat_model": {"ok": report.chat_ok, "error": report.chat_error},
        "models": {"chat": base.chat_model, "embed": base.embed_model},
        "note": "Sign in and pick a project to index PDFs and chat.",
    }


@app.post("/api/auth/register")
def auth_register(body: RegisterBody) -> TokenResponse:
    try:
        user = register_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = issue_token(user.id, user.email)
    return TokenResponse(access_token=token)


@app.post("/api/auth/login")
def auth_login(body: LoginBody) -> TokenResponse:
    user = authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenResponse(access_token=issue_token(user.id, user.email))


@app.get("/api/auth/me", response_model=UserOut)
def auth_me(user: Annotated[User, Depends(current_user)]) -> UserOut:
    return UserOut(id=user.id, email=user.email)


@app.post("/api/projects")
def projects_create(
    body: ProjectCreate,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    p = create_project(user.id, body.title)
    return p


@app.get("/api/projects")
def projects_list(user: Annotated[User, Depends(current_user)]) -> dict:
    items = list_projects(user.id)
    return {"projects": items}


@app.delete("/api/projects/{public_id}")
def projects_delete(
    public_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    if not delete_project_completely(public_id, user.id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


@app.get("/api/projects/{public_id}/health")
def project_health(
    public_id: str,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    if get_project_for_user(public_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    base = get_settings()
    settings = replace_chroma_path(base, project_index_dir(public_id))
    report = run_health(settings, include_index=True)
    ready = (
        report.ollama_ok
        and report.embed_ok
        and report.chat_ok
        and report.index_error is None
        and report.chunk_count > 0
    )
    return {
        "ready_for_chat": ready,
        "ollama": {"ok": report.ollama_ok, "error": report.ollama_error},
        "embed": {"ok": report.embed_ok, "dimension": report.embed_dim, "error": report.embed_error},
        "chat_model": {"ok": report.chat_ok, "error": report.chat_error},
        "index": {
            "chunk_count": report.chunk_count,
            "db_exists": report.index_db_exists,
            "path": str(settings.chroma_path),
            "error": report.index_error,
        },
        "models": {"chat": settings.chat_model, "embed": settings.embed_model},
        "note": None if report.chunk_count > 0 else "Upload PDFs to this project.",
    }


@app.post("/api/projects/{public_id}/chat")
def project_chat(
    public_id: str,
    body: ChatBody,
    user: Annotated[User, Depends(current_user)],
) -> dict:
    if get_project_for_user(public_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = _settings_for_project(public_id)
    try:
        reply = answer_question(settings, body.message.strip(), top_k=body.top_k)
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    touch_project(public_id)
    return {"reply": reply}


@app.post("/api/projects/{public_id}/ingest")
async def project_ingest(
    public_id: str,
    user: Annotated[User, Depends(current_user)],
    reset: bool = Form(False),
    files: list[UploadFile] = File(...),
) -> dict:
    if get_project_for_user(public_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    pdf_files = [f for f in files if f.filename and f.filename.lower().endswith(".pdf")]
    if len(pdf_files) != len(files):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    settings = _settings_for_project(public_id)
    tmp = Path(tempfile.mkdtemp(prefix="kamllm_upload_"))

    try:
        for uf in pdf_files:
            assert uf.filename is not None
            name = Path(uf.filename).name
            dest = tmp / name
            with dest.open("wb") as out:
                shutil.copyfileobj(uf.file, out)

        try:
            n = ingest_pdf_path(tmp, settings, reset=reset)
        except OllamaError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        touch_project(public_id)
        return {"chunks_indexed": n, "pdf_count": len(pdf_files)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    import uvicorn

    host = os.getenv("KAMLLM_API_HOST", "127.0.0.1")
    port = int(os.getenv("KAMLLM_API_PORT", "8765"))
    uvicorn.run("kamllm.api_main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
