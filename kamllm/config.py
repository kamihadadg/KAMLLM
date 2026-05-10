from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str
    chat_model: str
    embed_model: str
    chroma_path: Path  # Dir for SQLite chunks.sqlite
    chunk_size: int
    chunk_overlap: int
    top_k: int


def get_settings() -> Settings:
    load_dotenv(Path.cwd() / ".env", override=False)

    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    chroma = Path(os.getenv("CHROMA_PATH", ".chroma"))
    if not chroma.is_absolute():
        chroma = (Path.cwd() / chroma).resolve()

    return Settings(
        ollama_base_url=base,
        chat_model=os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5-coder:7b"),
        embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        chroma_path=chroma,
        chunk_size=max(100, int(os.getenv("CHUNK_CHAR_SIZE", "1200"))),
        chunk_overlap=max(0, int(os.getenv("CHUNK_CHAR_OVERLAP", "150"))),
        top_k=max(1, int(os.getenv("TOP_K_CHUNKS", "6"))),
    )
