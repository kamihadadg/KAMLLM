"""Shared RAG QA pipeline for CLI and HTTP API."""

from __future__ import annotations

from typing import Optional

from kamllm.config import Settings
from kamllm.llm.ollama import OllamaError, chat_completion
from kamllm.prompts import SYSTEM_PROMPT, USER_ANSWER_TEMPLATE
from kamllm.rag.retrieve import format_context_block, retrieve


def answer_question(
    settings: Settings,
    question: str,
    top_k: Optional[int] = None,
) -> str:
    chunks = retrieve(question, settings, top_k=top_k)
    blocks = "\n".join(format_context_block(c) for c in chunks)
    user_msg = USER_ANSWER_TEMPLATE.format(context=blocks, question=question)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    try:
        return chat_completion(settings, messages)
    except Exception as exc:  # noqa: BLE001
        raise OllamaError(str(exc)) from exc
