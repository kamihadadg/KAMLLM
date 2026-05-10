from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
import requests

from kamllm.config import Settings
from kamllm.llm.ollama import OllamaError, embed_many
from kamllm.rag.store import open_index


def _source_key(pdf_path: Path) -> str:
    resolved = pdf_path.resolve()
    digest = hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:10]
    return f"{resolved.stem}_{digest}"


def list_pdf_targets(target: Path) -> list[Path]:
    """Return PDF files given a single .pdf path or directory."""
    target = target.resolve()
    if target.is_file():
        if target.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {target}")
        return [target]
    if target.is_dir():
        pdfs = sorted(target.glob("*.pdf"))
        if not pdfs:
            raise ValueError(f"No PDF files in directory: {target}")
        return pdfs
    raise ValueError(f"Path does not exist: {target}")


def chunk_char_blocks(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-based chunks with overlap; keeps page citations exact (caller chunks per-page)."""
    text = text.replace("\x00", " ").strip()
    if not text:
        return []
    if overlap >= chunk_size:
        overlap = max(0, min(overlap, chunk_size // 4))

    chunks: list[str] = []
    pos = 0
    length = len(text)
    while pos < length:
        end = min(pos + chunk_size, length)
        block = text[pos:end].strip()
        if block:
            chunks.append(block)
        if end >= length:
            break
        step = chunk_size - overlap
        if step <= 0:
            step = max(1, chunk_size // 2)
        pos += step
    return chunks


def extract_page_texts(pdf_path: Path) -> tuple[str, dict[int, str]]:
    """
    Extract text per page. Returns stem label and mapping page_number (1-based) -> text.
    """
    texts: dict[int, str] = {}
    doc = fitz.open(pdf_path)
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            page_num = i + 1
            t = page.get_text("text") or ""
            if t.strip():
                texts[page_num] = t
    finally:
        doc.close()
    return pdf_path.name, texts


def ingest_pdf_path(
    target: Path,
    settings: Settings,
    *,
    reset: bool = False,
) -> int:
    """
    Encode all PDFs under target path into the local SQLite/NumPy index via Ollama embeddings.
    Returns number of chunks stored.
    """
    pdfs = list_pdf_targets(target)
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, object]] = []

    for pdf in pdfs:
        pdf_key = _source_key(pdf)
        try:
            name, pages = extract_page_texts(pdf)
        except Exception as exc:  # noqa: BLE001 - surface PDF errors cleanly
            raise OllamaError(f"Failed to read PDF {pdf}: {exc}") from exc

        if not pages:
            continue

        for page_no in sorted(pages.keys()):
            page_text = pages[page_no]
            blocks = chunk_char_blocks(page_text, settings.chunk_size, settings.chunk_overlap)
            for cidx, blk in enumerate(blocks):
                chunk_id = f"{pdf_key}:p{page_no}:c{cidx}"
                ids.append(chunk_id)
                documents.append(blk)
                metadatas.append(
                    {
                        "source_filename": name,
                        "source_path": str(pdf.resolve()),
                        "pdf_key": pdf_key,
                        "page": int(page_no),
                        "chunk_index": int(cidx),
                    }
                )

    if not ids:
        raise OllamaError("No text extracted from PDFs (scan-only PDF or empty files?).")

    try:
        vectors = embed_many(settings, documents)
    except requests.HTTPError as exc:
        raise OllamaError(f"Embedding request failed ({exc}); check embed model.") from exc

    idx = open_index(settings, reset=reset)
    try:
        idx.upsert_chunks(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)
        return len(ids)
    finally:
        idx.close()
