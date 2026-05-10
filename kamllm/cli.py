from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from kamllm.config import get_settings
from kamllm.diagnostics import run_health
from kamllm.llm.ollama import OllamaError
from kamllm.qa import answer_question
from kamllm.rag.ingest_pdf import ingest_pdf_path

app = typer.Typer(no_args_is_help=True, help="Local PDF RAG: Ollama + SQLite chunk index.")


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="PDF file or directory containing *.pdf"),
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Delete all chunks in the SQLite index before ingest (--reset clears previous PDF index)",
    ),
) -> None:
    settings = get_settings()
    typer.echo(f"Using embed model '{settings.embed_model}' from {settings.ollama_base_url}")
    typer.echo(f"Index dir: {settings.chroma_path}")
    try:
        n = ingest_pdf_path(path, settings, reset=reset)
    except Exception as exc:  # noqa: BLE001
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho(f"Indexed {n} chunk(s).", fg=typer.colors.GREEN)


@app.command()
def ask(
    question: str = typer.Argument(..., show_default=False),
    top_k: Optional[int] = typer.Option(None, "--top-k", help="Override TOP_K_CHUNKS from env"),
) -> None:
    settings = get_settings()
    try:
        out = answer_question(settings, question, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.echo(out)


@app.command("chat")
def chat_loop(
    top_k: Optional[int] = typer.Option(None, "--top-k", help="Override TOP_K_CHUNKS from env"),
) -> None:
    settings = get_settings()
    typer.echo("Interactive mode. Ctrl+C / exit / quit / \\q to stop.")
    while True:
        try:
            line = typer.prompt("you", prompt_suffix=" ").strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("")
            raise typer.Exit(code=0)
        if not line:
            continue
        if line.lower() in {"exit", "quit", "\\q"}:
            raise typer.Exit(code=0)
        try:
            out = answer_question(settings, line, top_k=top_k)
        except Exception as exc:  # noqa: BLE001
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
            continue
        typer.echo(out)
        typer.echo()


@app.command()
def doctor() -> None:
    settings = get_settings()
    ok = True
    typer.echo(f"OLLAMA_BASE_URL={settings.ollama_base_url}")
    report = run_health(settings)

    if report.ollama_ok:
        typer.secho("Ollama reachable: YES", fg=typer.colors.GREEN)
    else:
        ok = False
        typer.secho(f"Ollama reachable: NO ({report.ollama_error})", fg=typer.colors.RED)

    if report.embed_ok and report.embed_dim is not None:
        typer.secho(f"Embed model '{settings.embed_model}': YES (dim={report.embed_dim})", fg=typer.colors.GREEN)
    else:
        ok = False
        typer.secho(f"Embed model '{settings.embed_model}': NO ({report.embed_error})", fg=typer.colors.RED)

    if report.chat_ok:
        typer.secho(f"Chat model '{settings.chat_model}': YES", fg=typer.colors.GREEN)
    else:
        ok = False
        typer.secho(f"Chat model '{settings.chat_model}': NO ({report.chat_error})", fg=typer.colors.RED)

    if report.index_error is None:
        db = settings.chroma_path / "chunks.sqlite"
        typer.echo(f"Index dir: {settings.chroma_path}")
        typer.echo(
            f"SQLite DB: chunks.sqlite ({'exists' if db.is_file() else 'missing'}) | chunks: {report.chunk_count}",
        )
        if report.chunk_count == 0:
            typer.secho("Index empty: run `kamllm ingest <pdf-or-dir>`", fg=typer.colors.YELLOW)
    else:
        ok = False
        typer.secho(f"Index check failed: {report.index_error}", fg=typer.colors.RED)

    raise typer.Exit(code=0 if ok else 2)


if __name__ == "__main__":
    app()
