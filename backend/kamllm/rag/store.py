"""Persistent PDF chunk index backed by SQLite + NumPy cosine search (lightweight deps)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from kamllm.config import Settings


_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_path TEXT NOT NULL,
    pdf_key TEXT NOT NULL,
    page INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    document TEXT NOT NULL,
    embedding_blob BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pdf_key ON chunks(pdf_key);
"""


def index_db_path(settings: Settings) -> Path:
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    return settings.chroma_path / "chunks.sqlite"


class PdfChunkIndex:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def wipe(self) -> None:
        self._conn.execute("DELETE FROM chunks")
        self._conn.commit()

    def upsert_chunks(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        rows: list[tuple[Any, ...]] = []
        for cid, doc, meta, vec in zip(ids, documents, metadatas, embeddings, strict=True):
            blob = np.asarray(vec, dtype=np.float32).tobytes()
            rows.append(
                (
                    cid,
                    str(meta["source_filename"]),
                    str(meta["source_path"]),
                    str(meta["pdf_key"]),
                    int(meta["page"]),
                    int(meta["chunk_index"]),
                    doc,
                    blob,
                )
            )
        self._conn.executemany(
            "INSERT OR REPLACE INTO chunks(chunk_id, source_filename, source_path, pdf_key, page,"
            " chunk_index, document, embedding_blob) VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
        self._conn.commit()

    def count(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM chunks")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def top_k(self, query_embedding: list[float], k: int) -> list[tuple[str, str, dict[str, Any], float]]:
        """Return (chunk_id, document, meta, distance) with distance ≈ 1 - cosine_similarity."""

        q = np.asarray(query_embedding, dtype=np.float32)
        qnorm = np.linalg.norm(q) + np.float32(1e-12)

        cur = self._conn.execute(
            "SELECT chunk_id, document, source_filename, source_path, pdf_key, page,"
            " chunk_index, embedding_blob FROM chunks",
        )

        hits: list[tuple[float, str, str, dict[str, Any]]] = []
        for row in cur:
            vec = np.frombuffer(row["embedding_blob"], dtype=np.float32)
            vnorm = np.linalg.norm(vec) + np.float32(1e-12)
            sim = float(np.dot(q, vec) / (qnorm * vnorm))
            meta = {
                "source_filename": row["source_filename"],
                "source_path": row["source_path"],
                "pdf_key": row["pdf_key"],
                "page": int(row["page"]),
                "chunk_index": int(row["chunk_index"]),
            }
            hits.append((sim, str(row["chunk_id"]), str(row["document"]), meta))

        hits.sort(key=lambda item: item[0], reverse=True)

        top = hits[:k]
        out: list[tuple[str, str, dict[str, Any], float]] = []
        for sim, cid, doc, meta in top:
            out.append((cid, doc, meta, float(1.0 - sim)))
        return out


def open_index(settings: Settings, *, reset: bool = False) -> PdfChunkIndex:
    idx = PdfChunkIndex(index_db_path(settings))
    if reset:
        idx.wipe()
    return idx


def index_exists(settings: Settings) -> bool:
    return index_db_path(settings).is_file()


def count_chunks(settings: Settings) -> int:
    if not index_exists(settings):
        return 0
    idx = PdfChunkIndex(index_db_path(settings))
    try:
        return idx.count()
    finally:
        idx.close()
