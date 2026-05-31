from opencode_py.cli import _session_title_from_message
from opencode_py.session.models import SessionMeta


def test_session_title_from_message():
    assert _session_title_from_message(None) == "New session"
    assert _session_title_from_message(" hello ") == "hello"
    long = "x" * 200
    assert len(_session_title_from_message(long)) == 60


def test_session_meta_has_compaction_observability_defaults():
    session = SessionMeta(
        thread_id="thr_1",
        title="t",
        created_at=1.0,
        updated_at=1.0,
        cwd=".",
        provider="anthropic",
        model="claude",
    )
    assert session.compaction_trigger_count == 0
    assert session.last_overflow_reason is None
    assert session.last_token_counter_source is None
    assert session.last_compaction_tokens_before == 0
    assert session.last_compaction_tokens_after == 0
    assert session.last_compaction_ratio == 1.0
