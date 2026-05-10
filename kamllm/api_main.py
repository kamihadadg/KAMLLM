"""
HTTP API for the Next.js UI. Run from repo root (so `.env` applies):

    uvicorn kamllm.api_main:app --host 127.0.0.1 --port 8765

Or: python -m kamllm.api_main
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from kamllm.config import get_settings
from kamllm.diagnostics import run_health
from kamllm.llm.ollama import OllamaError
from kamllm.qa import answer_question
from kamllm.rag.ingest_pdf import ingest_pdf_path

ALLOWED_ORIGINS = os.getenv(
    "KAMLLM_CORS_ORIGINS",
    "http://127.0.0.1:3000,http://localhost:3000",
).split(",")

app = FastAPI(title="KAMLLM API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatBody(BaseModel):
    message: str = Field(..., min_length=1)
    top_k: int | None = Field(None, ge=1, le=50)


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    report = run_health(settings)
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
        "note": None if report.chunk_count > 0 else "Upload PDFs via the UI or run CLI ingest.",
    }


@app.post("/api/chat")
def chat(body: ChatBody) -> dict:
    settings = get_settings()
    try:
        answer = answer_question(settings, body.message.strip(), top_k=body.top_k)
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"reply": answer}


@app.post("/api/ingest")
async def ingest(
    reset: bool = Form(False),
    files: list[UploadFile] = File(...),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    pdf_files = [f for f in files if f.filename and f.filename.lower().endswith(".pdf")]
    if len(pdf_files) != len(files):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    settings = get_settings()
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
