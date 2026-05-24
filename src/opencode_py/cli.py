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
    provider = settings.provider.lower().strip()
    if provider == "anthropic":
        if not settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            console.print("[red]ANTHROPIC_API_KEY not set.[/red] Export it or put it in .env")
            raise typer.Exit(1)
        return

    if provider == "openai":
        if not settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            console.print("[red]OPENAI_API_KEY not set.[/red] Export it or put it in .env")
            raise typer.Exit(1)
        return

    console.print(f"[red]Unsupported provider: {settings.provider}[/red]")
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
                "agent": agent.model_dump(),
            }
            rendered_start = False
            async for event in graph.astream_events(state_in, config=cfg, version="v2"):
                name = event.get("event")
                data = event.get("data", {})

                if name == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    content = getattr(chunk, "content", None)
                    if isinstance(content, str) and content:
                        if not rendered_start:
                            console.print()
                            console.print("assistant› ", end="")
                            rendered_start = True
                        console.print(content, end="")
                    elif isinstance(content, list):
                        text = "".join(
                            part.get("text", "")
                            for part in content
                            if isinstance(part, dict) and part.get("type") == "text"
                        )
                        if text:
                            if not rendered_start:
                                console.print()
                                console.print("assistant› ", end="")
                                rendered_start = True
                            console.print(text, end="")

                if name == "on_chain_end" and event.get("name") == "exec_tools":
                    output = data.get("output") or {}
                    msgs = output.get("messages") or []
                    if msgs:
                        console.print()
                        console.print(f"[dim]tools: executed {len(msgs)} call(s)[/dim]")

            if rendered_start:
                console.print()

            result = await graph.aget_state(cfg)
            values = result.values
            messages = values.get("messages", []) if isinstance(values, dict) else []
            for m in reversed(messages):
                if isinstance(m, AIMessage):
                    text = m.content if isinstance(m.content, str) else "".join(
                        b.get("text", "") for b in m.content if isinstance(b, dict) and b.get("type") == "text"
                    )
                    if text and not rendered_start:
                        console.print()
                        console.print(Markdown(f"**assistant›** {text}"))
                    break
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
    console.print(f"provider: {settings.provider}")
    console.print(f"model: {settings.model}")
    console.print(f"data dir: {settings.data_dir}")
    console.print(f"db: {settings.session_db_path()}")
    console.print(f"anthropic base url: {settings.anthropic_base_url or '(default)'}")
    console.print(f"openai base url: {settings.openai_base_url or '(default)'}")
    console.print(f"api key set: {bool(settings.anthropic_api_key or os.environ.get('ANTHROPIC_API_KEY') or settings.openai_api_key or os.environ.get('OPENAI_API_KEY'))}")


if __name__ == "__main__":
    app()
