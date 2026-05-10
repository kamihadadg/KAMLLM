from __future__ import annotations

from typing import Any

import requests

from kamllm.config import Settings


class OllamaError(RuntimeError):
    pass


def _chat_url(settings: Settings) -> str:
    return f"{settings.ollama_base_url}/api/chat"


def _parse_embedding_payload(body: dict[str, Any]) -> list[list[float]]:
    """Support /api/embed (embeddings[][] ) and legacy /api/embeddings (embedding[])."""
    raw = body.get("embeddings")
    if isinstance(raw, list) and raw:
        rows: list[list[float]] = []
        for row in raw:
            if isinstance(row, list) and row:
                rows.append([float(x) for x in row])
        if rows:
            return rows

    legacy = body.get("embedding")
    if isinstance(legacy, list) and legacy:
        return [[float(x) for x in legacy]]

    raise OllamaError(f"Unexpected embed response: {body!r}")


def _post_embed(settings: Settings, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    base = settings.ollama_base_url
    r = requests.post(f"{base}/api/embed", json=payload, timeout=timeout_s)
    if r.status_code == 404:
        legacy_payload = {"model": payload["model"], "prompt": payload.get("input", "")}
        if isinstance(payload.get("input"), list):
            raise OllamaError(
                "/api/embed returned 404; legacy /api/embeddings does not batch multiple inputs.",
            )
        r = requests.post(f"{base}/api/embeddings", json=legacy_payload, timeout=timeout_s)
    r.raise_for_status()
    return r.json()


def embed_one(settings: Settings, text: str, timeout_s: float = 120.0) -> list[float]:
    if not text.strip():
        raise OllamaError("Cannot embed empty text")
    body = _post_embed(
        settings,
        {"model": settings.embed_model, "input": text},
        timeout_s,
    )
    rows = _parse_embedding_payload(body)
    return rows[0]


def embed_many(
    settings: Settings,
    texts: list[str],
    timeout_s: float = 120.0,
) -> list[list[float]]:
    """Sequential embeddings against Ollama (/api/embed preferred, legacy fallback)."""
    return [embed_one(settings, str(t), timeout_s=timeout_s) for t in texts]


def chat_completion(
    settings: Settings,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
    timeout_s: float = 300.0,
) -> str:
    resp = requests.post(
        _chat_url(settings),
        json={
            "model": settings.chat_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=timeout_s,
    )
    resp.raise_for_status()
    body = resp.json()
    msg = body.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OllamaError(f"No message content from Ollama: {body!r}")
    return content.strip()


def ping(settings: Settings, timeout_s: float = 5.0) -> None:
    r = requests.get(f"{settings.ollama_base_url}/api/version", timeout=timeout_s)
    r.raise_for_status()
