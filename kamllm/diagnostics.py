"""Health checks shared by CLI `doctor` and the HTTP API."""

from __future__ import annotations

from dataclasses import dataclass

from kamllm.config import Settings
from kamllm.llm.ollama import chat_completion, embed_one, ping
from kamllm.rag.store import count_chunks


@dataclass
class HealthReport:
    ollama_ok: bool
    embed_ok: bool
    chat_ok: bool
    embed_dim: int | None
    chunk_count: int
    index_db_exists: bool
    ollama_error: str | None
    embed_error: str | None
    chat_error: str | None
    index_error: str | None

    @property
    def all_ok(self) -> bool:
        return (
            self.ollama_ok
            and self.embed_ok
            and self.chat_ok
            and self.index_error is None
        )


def run_health(settings: Settings) -> HealthReport:
    o_err = e_err = c_err = i_err = None
    o_ok = e_ok = c_ok = False
    dim: int | None = None
    n = 0
    db_exists = False

    try:
        ping(settings)
        o_ok = True
    except Exception as exc:  # noqa: BLE001
        o_err = str(exc)

    try:
        emb = embed_one(settings, "kamllm healthcheck")
        dim = len(emb)
        e_ok = True
    except Exception as exc:  # noqa: BLE001
        e_err = str(exc)

    try:
        msg = [{"role": "user", "content": "Reply with OK only."}]
        chat_completion(settings, msg, timeout_s=120.0)
        c_ok = True
    except Exception as exc:  # noqa: BLE001
        c_err = str(exc)

    try:
        n = count_chunks(settings)
        db_exists = (settings.chroma_path / "chunks.sqlite").is_file()
    except Exception as exc:  # noqa: BLE001
        i_err = str(exc)

    return HealthReport(
        ollama_ok=o_ok,
        embed_ok=e_ok,
        chat_ok=c_ok,
        embed_dim=dim,
        chunk_count=n,
        index_db_exists=db_exists,
        ollama_error=o_err,
        embed_error=e_err,
        chat_error=c_err,
        index_error=i_err,
    )
