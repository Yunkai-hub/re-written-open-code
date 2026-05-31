from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from opencode_py.session.models import SessionForkMeta, SessionMeta


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(db_path: Path) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_meta (
                thread_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                cwd TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                parent_thread_id TEXT,
                fork_checkpoint_id TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                compaction_count INTEGER NOT NULL DEFAULT 0,
                compaction_trigger_count INTEGER NOT NULL DEFAULT 0,
                last_compacted_at REAL,
                last_user_preview TEXT,
                last_overflow_reason TEXT,
                last_token_counter_source TEXT,
                last_compaction_tokens_before INTEGER NOT NULL DEFAULT 0,
                last_compaction_tokens_after INTEGER NOT NULL DEFAULT 0,
                last_compaction_ratio REAL NOT NULL DEFAULT 1.0,
                archived INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(session_meta)").fetchall()
        }

        migrations: list[tuple[str, str]] = [
            ("compaction_trigger_count", "ALTER TABLE session_meta ADD COLUMN compaction_trigger_count INTEGER NOT NULL DEFAULT 0"),
            ("last_overflow_reason", "ALTER TABLE session_meta ADD COLUMN last_overflow_reason TEXT"),
            ("last_token_counter_source", "ALTER TABLE session_meta ADD COLUMN last_token_counter_source TEXT"),
            ("last_compaction_tokens_before", "ALTER TABLE session_meta ADD COLUMN last_compaction_tokens_before INTEGER NOT NULL DEFAULT 0"),
            ("last_compaction_tokens_after", "ALTER TABLE session_meta ADD COLUMN last_compaction_tokens_after INTEGER NOT NULL DEFAULT 0"),
            ("last_compaction_ratio", "ALTER TABLE session_meta ADD COLUMN last_compaction_ratio REAL NOT NULL DEFAULT 1.0"),
        ]
        for col, sql in migrations:
            if col not in existing_cols:
                conn.execute(sql)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_fork (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_thread_id TEXT NOT NULL,
                target_thread_id TEXT NOT NULL,
                fork_checkpoint_id TEXT,
                created_at REAL NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_session(db_path: Path, meta: SessionMeta) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO session_meta (
                thread_id, title, created_at, updated_at, cwd, provider, model,
                parent_thread_id, fork_checkpoint_id, message_count, compaction_count,
                compaction_trigger_count, last_compacted_at, last_user_preview,
                last_overflow_reason, last_token_counter_source,
                last_compaction_tokens_before, last_compaction_tokens_after,
                last_compaction_ratio, archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                title=excluded.title,
                updated_at=excluded.updated_at,
                cwd=excluded.cwd,
                provider=excluded.provider,
                model=excluded.model,
                parent_thread_id=excluded.parent_thread_id,
                fork_checkpoint_id=excluded.fork_checkpoint_id,
                message_count=excluded.message_count,
                compaction_count=excluded.compaction_count,
                compaction_trigger_count=excluded.compaction_trigger_count,
                last_compacted_at=excluded.last_compacted_at,
                last_user_preview=excluded.last_user_preview,
                last_overflow_reason=excluded.last_overflow_reason,
                last_token_counter_source=excluded.last_token_counter_source,
                last_compaction_tokens_before=excluded.last_compaction_tokens_before,
                last_compaction_tokens_after=excluded.last_compaction_tokens_after,
                last_compaction_ratio=excluded.last_compaction_ratio,
                archived=excluded.archived
            """,
            (
                meta.thread_id,
                meta.title,
                meta.created_at,
                meta.updated_at,
                meta.cwd,
                meta.provider,
                meta.model,
                meta.parent_thread_id,
                meta.fork_checkpoint_id,
                meta.message_count,
                meta.compaction_count,
                meta.compaction_trigger_count,
                meta.last_compacted_at,
                meta.last_user_preview,
                meta.last_overflow_reason,
                meta.last_token_counter_source,
                meta.last_compaction_tokens_before,
                meta.last_compaction_tokens_after,
                meta.last_compaction_ratio,
                1 if meta.archived else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def touch_session(
    db_path: Path,
    thread_id: str,
    *,
    title: str | None = None,
    message_count: int | None = None,
    compaction_count: int | None = None,
    compaction_trigger_count: int | None = None,
    last_compacted_at: float | None = None,
    last_user_preview: str | None = None,
    last_overflow_reason: str | None = None,
    last_token_counter_source: str | None = None,
    last_compaction_tokens_before: int | None = None,
    last_compaction_tokens_after: int | None = None,
    last_compaction_ratio: float | None = None,
) -> None:
    conn = _connect(db_path)
    try:
        updates: list[str] = ["updated_at = ?"]
        values: list[object] = [time.time()]

        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if message_count is not None:
            updates.append("message_count = ?")
            values.append(message_count)
        if compaction_count is not None:
            updates.append("compaction_count = ?")
            values.append(compaction_count)
        if compaction_trigger_count is not None:
            updates.append("compaction_trigger_count = ?")
            values.append(compaction_trigger_count)
        if last_compacted_at is not None:
            updates.append("last_compacted_at = ?")
            values.append(last_compacted_at)
        if last_user_preview is not None:
            updates.append("last_user_preview = ?")
            values.append(last_user_preview)
        if last_overflow_reason is not None:
            updates.append("last_overflow_reason = ?")
            values.append(last_overflow_reason)
        if last_token_counter_source is not None:
            updates.append("last_token_counter_source = ?")
            values.append(last_token_counter_source)
        if last_compaction_tokens_before is not None:
            updates.append("last_compaction_tokens_before = ?")
            values.append(last_compaction_tokens_before)
        if last_compaction_tokens_after is not None:
            updates.append("last_compaction_tokens_after = ?")
            values.append(last_compaction_tokens_after)
        if last_compaction_ratio is not None:
            updates.append("last_compaction_ratio = ?")
            values.append(last_compaction_ratio)

        values.append(thread_id)
        sql = f"UPDATE session_meta SET {', '.join(updates)} WHERE thread_id = ?"
        conn.execute(sql, tuple(values))
        conn.commit()
    finally:
        conn.close()


def list_sessions(db_path: Path, limit: int = 50, roots_only: bool = False) -> list[SessionMeta]:
    conn = _connect(db_path)
    try:
        where = "WHERE archived = 0"
        if roots_only:
            where += " AND parent_thread_id IS NULL"
        cur = conn.execute(
            f"""
            SELECT thread_id, title, created_at, updated_at, cwd, provider, model,
                   parent_thread_id, fork_checkpoint_id, message_count, compaction_count,
                   compaction_trigger_count, last_compacted_at, last_user_preview,
                   last_overflow_reason, last_token_counter_source,
                   last_compaction_tokens_before, last_compaction_tokens_after,
                   last_compaction_ratio, archived
            FROM session_meta
            {where}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            SessionMeta(
                thread_id=row["thread_id"],
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                cwd=row["cwd"],
                provider=row["provider"],
                model=row["model"],
                parent_thread_id=row["parent_thread_id"],
                fork_checkpoint_id=row["fork_checkpoint_id"],
                message_count=row["message_count"],
                compaction_count=row["compaction_count"],
                compaction_trigger_count=row["compaction_trigger_count"],
                last_compacted_at=row["last_compacted_at"],
                last_user_preview=row["last_user_preview"],
                last_overflow_reason=row["last_overflow_reason"],
                last_token_counter_source=row["last_token_counter_source"],
                last_compaction_tokens_before=row["last_compaction_tokens_before"],
                last_compaction_tokens_after=row["last_compaction_tokens_after"],
                last_compaction_ratio=row["last_compaction_ratio"],
                archived=bool(row["archived"]),
            )
            for row in rows
        ]
    finally:
        conn.close()


def record_fork(
    db_path: Path,
    source_thread_id: str,
    target_thread_id: str,
    fork_checkpoint_id: str | None = None,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO session_fork (source_thread_id, target_thread_id, fork_checkpoint_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (source_thread_id, target_thread_id, fork_checkpoint_id, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def get_session(db_path: Path, thread_id: str) -> SessionMeta | None:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT thread_id, title, created_at, updated_at, cwd, provider, model,
                   parent_thread_id, fork_checkpoint_id, message_count, compaction_count,
                   compaction_trigger_count, last_compacted_at, last_user_preview,
                   last_overflow_reason, last_token_counter_source,
                   last_compaction_tokens_before, last_compaction_tokens_after,
                   last_compaction_ratio, archived
            FROM session_meta
            WHERE thread_id = ?
            """,
            (thread_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return SessionMeta(
            thread_id=row["thread_id"],
            title=row["title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            cwd=row["cwd"],
            provider=row["provider"],
            model=row["model"],
            parent_thread_id=row["parent_thread_id"],
            fork_checkpoint_id=row["fork_checkpoint_id"],
            message_count=row["message_count"],
            compaction_count=row["compaction_count"],
            compaction_trigger_count=row["compaction_trigger_count"],
            last_compacted_at=row["last_compacted_at"],
            last_user_preview=row["last_user_preview"],
            last_overflow_reason=row["last_overflow_reason"],
            last_token_counter_source=row["last_token_counter_source"],
            last_compaction_tokens_before=row["last_compaction_tokens_before"],
            last_compaction_tokens_after=row["last_compaction_tokens_after"],
            last_compaction_ratio=row["last_compaction_ratio"],
            archived=bool(row["archived"]),
        )
    finally:
        conn.close()


def make_session_meta(
    thread_id: str,
    *,
    cwd: str,
    provider: str,
    model: str,
    title: str,
    parent_thread_id: str | None = None,
    fork_checkpoint_id: str | None = None,
) -> SessionMeta:
    now = time.time()
    return SessionMeta(
        thread_id=thread_id,
        title=title,
        created_at=now,
        updated_at=now,
        cwd=cwd,
        provider=provider,
        model=model,
        parent_thread_id=parent_thread_id,
        fork_checkpoint_id=fork_checkpoint_id,
    )


def make_fork_meta(
    source_thread_id: str,
    target_thread_id: str,
    fork_checkpoint_id: str | None = None,
) -> SessionForkMeta:
    return SessionForkMeta(
        source_thread_id=source_thread_id,
        target_thread_id=target_thread_id,
        fork_checkpoint_id=fork_checkpoint_id,
        created_at=time.time(),
    )
