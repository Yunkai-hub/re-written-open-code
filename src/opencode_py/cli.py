from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import typer
from langchain_core.messages import AIMessage, HumanMessage
from rich.console import Console
from rich.markdown import Markdown

from opencode_py.agent.graph import AsyncSqliteSaver, build_graph
from opencode_py.config import settings
from opencode_py.session.models import AgentConfig

app = typer.Typer(add_completion=False, help="opencode-py — Python reimplementation of opencode on LangGraph.")
console = Console()


def _ensure_key() -> None:
    if not settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY not set.[/red] Export it or put it in .env")
        raise typer.Exit(1)


async def _run_chat(thread_id: str, initial_message: str | None) -> None:
    db_path = str(settings.session_db_path())
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        graph = build_graph(checkpointer=saver)
        cfg = {"configurable": {"thread_id": thread_id}}
        agent = AgentConfig(model=settings.model, max_steps=settings.max_steps)
        cwd = str(Path.cwd())

        console.print(f"[dim]session: {thread_id}  model: {agent.model}  cwd: {cwd}[/dim]")
        first = initial_message

        while True:
            user_text = first or console.input("[bold cyan]you›[/bold cyan] ").strip()
            first = None
            if not user_text:
                continue
            if user_text in ("/exit", "/quit"):
                break

            state_in = {
                "messages": [HumanMessage(content=user_text)],
                "cwd": cwd,
                "agent": agent,
            }
            result = await graph.ainvoke(state_in, config=cfg)
            for m in result["messages"]:
                if isinstance(m, AIMessage):
                    text = m.content if isinstance(m.content, str) else "".join(
                        b.get("text", "") for b in m.content if isinstance(b, dict) and b.get("type") == "text"
                    )
                    if text:
                        console.print()
                        console.print(Markdown(f"**assistant›** {text}"))
            console.print()


@app.command()
def chat(message: str | None = typer.Argument(None, help="Optional first message; otherwise enter REPL.")) -> None:
    """Start a new chat session."""
    _ensure_key()
    thread_id = f"thr_{uuid.uuid4().hex[:12]}"
    asyncio.run(_run_chat(thread_id, message))


@app.command()
def resume(thread_id: str, message: str | None = typer.Argument(None)) -> None:
    """Resume a prior session by thread_id."""
    _ensure_key()
    asyncio.run(_run_chat(thread_id, message))


@app.command()
def doctor() -> None:
    """Show environment info."""
    console.print(f"model: {settings.model}")
    console.print(f"data dir: {settings.data_dir}")
    console.print(f"db: {settings.session_db_path()}")
    console.print(f"api key set: {bool(settings.anthropic_api_key or os.environ.get('ANTHROPIC_API_KEY'))}")


if __name__ == "__main__":
    app()
