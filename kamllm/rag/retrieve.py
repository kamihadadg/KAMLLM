from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kamllm.config import Settings
from kamllm.llm.ollama import embed_one
from kamllm.rag.store import PdfChunkIndex, index_db_path, index_exists


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    meta: dict[str, Any]
    distance: float | None


def retrieve(
    question: str,
    settings: Settings,
    *,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Semantic search over indexed PDF chunks (full scan; fine for modest corpora)."""
    k = settings.top_k if top_k is None else top_k

    if not index_exists(settings):
        raise RuntimeError("Index missing. Run `kamllm ingest …` first.")

    q_emb = embed_one(settings, question)
    idx = PdfChunkIndex(index_db_path(settings))
    try:
        if idx.count() == 0:
            raise RuntimeError("Index is empty. Run `kamllm ingest …` first.")
        hits = idx.top_k(q_emb, k)
    finally:
        idx.close()

    out: list[RetrievedChunk] = []
    for chunk_id, text, meta, dist in hits:
        out.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                text=text,
                meta=dict(meta),
                distance=float(dist),
            )
        )
    return out


def format_context_block(chunk: RetrievedChunk) -> str:
    """Single CONTEXT block header for the LLM citing filename + page + chunk."""
    fname = str(chunk.meta.get("source_filename", "unknown.pdf"))
    page = chunk.meta.get("page", "?")
    header = f"[source={fname} page={page} chunk_id={chunk.chunk_id}]"
    return f"{header}\n{chunk.text.strip()}\n"
