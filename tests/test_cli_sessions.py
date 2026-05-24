from opencode_py.cli import _session_title_from_message


def test_session_title_from_message():
    assert _session_title_from_message(None) == "New session"
    assert _session_title_from_message(" hello ") == "hello"
    long = "x" * 200
    assert len(_session_title_from_message(long)) == 60
