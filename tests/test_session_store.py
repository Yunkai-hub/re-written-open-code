import time
from pathlib import Path

from opencode_py.session.store import (
    get_session,
    init_schema,
    list_sessions,
    make_session_meta,
    record_fork,
    touch_session,
    upsert_session,
)


def test_session_store_upsert_list_touch(tmp_path: Path):
    db = tmp_path / "sessions.sqlite"
    init_schema(db)

    meta = make_session_meta(
        "thr_1",
        cwd=str(tmp_path),
        provider="anthropic",
        model="claude",
        title="t1",
    )
    upsert_session(db, meta)

    rows = list_sessions(db)
    assert len(rows) == 1
    assert rows[0].thread_id == "thr_1"

    touch_session(
        db,
        "thr_1",
        title="new title",
        message_count=10,
        compaction_count=1,
        compaction_trigger_count=2,
        last_overflow_reason="threshold",
        last_token_counter_source="provider",
        last_compaction_tokens_before=1200,
        last_compaction_tokens_after=700,
        last_compaction_ratio=0.5833,
    )
    session = get_session(db, "thr_1")
    assert session is not None
    assert session.title == "new title"
    assert session.message_count == 10
    assert session.compaction_count == 1
    assert session.compaction_trigger_count == 2
    assert session.last_overflow_reason == "threshold"
    assert session.last_token_counter_source == "provider"
    assert session.last_compaction_tokens_before == 1200
    assert session.last_compaction_tokens_after == 700
    assert session.last_compaction_ratio == 0.5833


def test_session_store_record_fork(tmp_path: Path):
    db = tmp_path / "sessions.sqlite"
    init_schema(db)

    meta1 = make_session_meta("thr_src", cwd=str(tmp_path), provider="anthropic", model="claude", title="src")
    meta2 = make_session_meta("thr_dst", cwd=str(tmp_path), provider="anthropic", model="claude", title="dst", parent_thread_id="thr_src")
    upsert_session(db, meta1)
    upsert_session(db, meta2)

    record_fork(db, "thr_src", "thr_dst", fork_checkpoint_id="cp_1")
    dst = get_session(db, "thr_dst")
    assert dst is not None
    assert dst.parent_thread_id == "thr_src"
