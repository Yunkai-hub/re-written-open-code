from __future__ import annotations

import asyncio
import os
import sqlite3
import uuid
from pathlib import Path

import typer
from langchain_core.messages import AIMessage, HumanMessage
from rich.console import Console
from rich.markdown import Markdown

from opencode_py.agent.graph import AsyncSqliteSaver, build_graph
from opencode_py.config import settings
from opencode_py.session.models import AgentConfig, SessionMeta
from opencode_py.session.store import (
    get_session,
    init_schema,
    list_sessions,
    make_session_meta,
    record_fork,
    touch_session,
    upsert_session,
)

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


def _session_title_from_message(message: str | None) -> str:
    if not message:
        return "New session"
    text = message.strip()
    return text[:60] if len(text) > 60 else text


def _print_sessions_for_pick(rows: list[SessionMeta]) -> None:
    for idx, s in enumerate(rows, start=1):
        parent = f" parent={s.parent_thread_id}" if s.parent_thread_id else ""
        console.print(
            f"[{idx}] {s.thread_id}  [{s.provider}/{s.model}]  msgs={s.message_count}  compact={s.compaction_count} trig={s.compaction_trigger_count}{parent}\n"
            f"    title: {s.title}\n"
            f"    cwd: {s.cwd}\n"
            f"    overflow={s.last_overflow_reason or '-'} counter={s.last_token_counter_source or '-'} ratio={s.last_compaction_ratio:.3f}"
        )


def _pick_session_interactively(db_path: Path, current_thread_id: str) -> str | None:
    rows = list_sessions(db_path, limit=50)
    if not rows:
        console.print("No sessions yet.")
        return None

    console.print("\n[bold]Available sessions[/bold]")
    _print_sessions_for_pick(rows)
    choice = console.input("Select session index/thread_id (empty to cancel): ").strip()
    if not choice:
        return None

    selected: str | None = None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(rows):
            selected = rows[idx - 1].thread_id
    else:
        selected = choice

    if not selected:
        console.print("[yellow]Invalid selection.[/yellow]")
        return None

    if get_session(db_path, selected) is None:
        console.print(f"[yellow]Session not found:[/yellow] {selected}")
        return None

    if selected == current_thread_id:
        console.print("[dim]Already on this session.[/dim]")
        return selected

    return selected


def _copy_thread_sqlite_fallback(db_path: Path, source_thread_id: str, target_thread_id: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO checkpoints (
                    thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata
                )
                SELECT ?, checkpoint_ns, checkpoint_id, parent_checkpoint_id, type, checkpoint, metadata
                FROM checkpoints
                WHERE thread_id = ?
                """,
                (target_thread_id, source_thread_id),
            )
            conn.execute(
                """
                INSERT INTO writes (
                    thread_id, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value
                )
                SELECT ?, checkpoint_ns, checkpoint_id, task_id, idx, channel, type, value
                FROM writes
                WHERE thread_id = ?
                """,
                (target_thread_id, source_thread_id),
            )
    finally:
        conn.close()


async def _run_chat(thread_id: str, initial_message: str | None, parent_thread_id: str | None = None) -> None:
    db_path = settings.session_db_path()
    init_schema(db_path)

    async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
        graph = build_graph(checkpointer=saver)
        cfg = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": max(120, settings.max_steps * 8),
        }
        agent = AgentConfig(model=settings.model, max_steps=settings.max_steps)
        cwd = str(Path.cwd())

        existing = get_session(db_path, thread_id)
        if existing is None:
            meta = make_session_meta(
                thread_id,
                cwd=cwd,
                provider=settings.provider,
                model=agent.model,
                title=_session_title_from_message(initial_message),
                parent_thread_id=parent_thread_id,
            )
            upsert_session(db_path, meta)

        console.print(f"[dim]session: {thread_id}  model: {agent.model}  cwd: {cwd}[/dim]")
        first = initial_message

        while True:
            user_text = first or console.input("[bold cyan]you>[/bold cyan] ").strip()
            first = None
            if not user_text:
                continue
            if user_text in ("/exit", "/quit"):
                break

            if user_text.strip().lower() == "/sessions":
                selected = _pick_session_interactively(db_path, thread_id)
                if selected and selected != thread_id:
                    thread_id = selected
                    cfg = {
                        "configurable": {"thread_id": thread_id},
                        "recursion_limit": max(120, settings.max_steps * 8),
                    }
                    resumed = get_session(db_path, thread_id)
                    if resumed:
                        console.print(f"[green]Switched to session:[/green] {thread_id}  [dim]{resumed.title}[/dim]")
                    else:
                        console.print(f"[green]Switched to session:[/green] {thread_id}")
                continue

            compact_cmd = user_text.strip().lower()
            compact_only = compact_cmd in {"/compact", "/compat"}
            state_in = {
                "cwd": cwd,
                "session_id": thread_id,
                "agent": agent.model_dump(),
            }
            if compact_only:
                state_in["force_compact"] = True
                state_in["compact_only"] = True
            else:
                state_in["messages"] = [HumanMessage(content=user_text)]
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
                            console.print("assistant> ", end="")
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
                                console.print("assistant> ", end="")
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
            values = result.values if isinstance(result.values, dict) else {}
            messages = values.get("messages", [])
            compaction_count = values.get("compaction_count", 0)
            compaction_trigger_count = int(values.get("compaction_trigger_count", 0) or 0)

            if compact_only:
                summary = values.get("last_compaction_summary") or ""
                console.print("[green]Compaction completed.[/green]")
                if summary:
                    preview = summary[:240] + ("..." if len(summary) > 240 else "")
                    console.print(f"[dim]summary:[/dim] {preview}")
            else:
                for m in reversed(messages):
                    if isinstance(m, AIMessage):
                        text = m.content if isinstance(m.content, str) else "".join(
                            b.get("text", "") for b in m.content if isinstance(b, dict) and b.get("type") == "text"
                        )
                        if text and not rendered_start:
                            console.print()
                            console.print(Markdown(f"**assistant>** {text}"))
                        break

            total_in = 0
            total_out = 0
            turn_in = 0
            turn_out = 0
            latest_ai = None
            for m in messages:
                if isinstance(m, AIMessage):
                    latest_ai = m
                    usage = getattr(m, "usage_metadata", None) or {}
                    total_in += int(usage.get("input_tokens", 0) or usage.get("input_token_count", 0) or 0)
                    total_out += int(usage.get("output_tokens", 0) or usage.get("output_token_count", 0) or 0)

            if isinstance(latest_ai, AIMessage):
                usage = getattr(latest_ai, "usage_metadata", None) or {}
                turn_in = int(usage.get("input_tokens", 0) or usage.get("input_token_count", 0) or 0)
                turn_out = int(usage.get("output_tokens", 0) or usage.get("output_token_count", 0) or 0)

            estimated_tokens = int(values.get("estimated_tokens", 0) or 0)
            estimated_payload_tokens = int(values.get("estimated_payload_tokens", 0) or 0)
            calibration_ratio = float(values.get("runtime_ctx_calibration_ratio", 1.0) or 1.0)
            overflow_reason = str(values.get("overflow_reason", "none") or "none")
            token_counter_source = str(values.get("token_counter_source", "fallback") or "fallback")
            compaction_before = int(values.get("compaction_visible_tokens_before", estimated_tokens) or estimated_tokens)
            compaction_after = int(values.get("compaction_visible_tokens_after", estimated_tokens) or estimated_tokens)
            compaction_ratio = float(values.get("compaction_last_ratio", 1.0) or 1.0)
            console.print(
                f"[dim]tokens(turn): in={turn_in} out={turn_out} | total: in={total_in} out={total_out} | estimated_ctx={estimated_tokens} payload_est={estimated_payload_tokens} calib={calibration_ratio:.3f} compact={int(compaction_count or 0)} trig={compaction_trigger_count} overflow={overflow_reason} counter={token_counter_source} window={compaction_before}->{compaction_after} ratio={compaction_ratio:.3f}[/dim]"
            )

            touch_session(
                db_path,
                thread_id,
                message_count=len(messages),
                compaction_count=int(compaction_count or 0),
                compaction_trigger_count=compaction_trigger_count,
                last_compacted_at=(float(values.get("last_compacted_at")) if values.get("last_compacted_at") is not None else None),
                last_user_preview=(user_text if not compact_only else "/compact")[:200],
                last_overflow_reason=overflow_reason,
                last_token_counter_source=token_counter_source,
                last_compaction_tokens_before=compaction_before,
                last_compaction_tokens_after=compaction_after,
                last_compaction_ratio=compaction_ratio,
            )
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


@app.command("sessions")
def sessions_cmd(limit: int = typer.Option(20, min=1, max=200)) -> None:
    """List sessions metadata."""
    db_path = settings.session_db_path()
    init_schema(db_path)
    rows = list_sessions(db_path, limit=limit)
    if not rows:
        console.print("No sessions yet.")
        return

    for s in rows:
        parent = f" parent={s.parent_thread_id}" if s.parent_thread_id else ""
        console.print(
            f"- {s.thread_id}  [{s.provider}/{s.model}]  msgs={s.message_count}  compact={s.compaction_count} trig={s.compaction_trigger_count}{parent}\n"
            f"  title: {s.title}\n"
            f"  cwd: {s.cwd}\n"
            f"  overflow={s.last_overflow_reason or '-'} counter={s.last_token_counter_source or '-'} ratio={s.last_compaction_ratio:.3f}"
        )


@app.command("fork")
def fork_cmd(
    thread_id: str,
    new_thread_id: str | None = typer.Option(None, help="Optional explicit target thread id."),
    title: str | None = typer.Option(None, help="Optional title for new fork session."),
) -> None:
    """Fork a session into a new thread."""
    db_path = settings.session_db_path()
    init_schema(db_path)

    source_meta = get_session(db_path, thread_id)
    if source_meta is None:
        console.print(f"[red]Source session not found:[/red] {thread_id}")
        raise typer.Exit(1)

    target_thread = new_thread_id or f"thr_{uuid.uuid4().hex[:12]}"

    async def _copy() -> None:
        async with AsyncSqliteSaver.from_conn_string(str(db_path)) as saver:
            await saver.acopy_thread(thread_id, target_thread)

    try:
        asyncio.run(_copy())
    except NotImplementedError:
        _copy_thread_sqlite_fallback(db_path, thread_id, target_thread)

    meta = make_session_meta(
        target_thread,
        cwd=source_meta.cwd,
        provider=source_meta.provider,
        model=source_meta.model,
        title=title or f"Fork of {source_meta.thread_id}",
        parent_thread_id=thread_id,
    )
    upsert_session(db_path, meta)
    record_fork(db_path, source_thread_id=thread_id, target_thread_id=target_thread)

    console.print(f"Forked {thread_id} -> {target_thread}")


@app.command()
def doctor() -> None:
    """Show environment info."""
    console.print(f"provider: {settings.provider}")
    console.print(f"model: {settings.model}")
    console.print(f"data dir: {settings.data_dir}")
    console.print(f"db: {settings.session_db_path()}")
    console.print(f"anthropic base url: {settings.anthropic_base_url or '(default)'}")
    console.print(f"openai base url: {settings.openai_base_url or '(default)'}")
    console.print(f"context window: {settings.context_window_tokens}")
    console.print(f"compaction enabled: {settings.compaction_enabled}")
    console.print(f"compaction trigger tokens: {settings.compaction_trigger_tokens()}")
    console.print(
        f"api key set: {bool(settings.anthropic_api_key or os.environ.get('ANTHROPIC_API_KEY') or settings.openai_api_key or os.environ.get('OPENAI_API_KEY'))}"
    )


if __name__ == "__main__":
    app()
