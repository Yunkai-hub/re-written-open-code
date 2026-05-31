from opencode_py.cli import _session_title_from_message
from opencode_py.mcp.manager import MCPBootstrapResult


def test_session_title_from_message_still_works():
    assert _session_title_from_message(" hello ") == "hello"


def test_mcp_bootstrap_result_defaults():
    result = MCPBootstrapResult(enabled=False)
    assert result.enabled is False
    assert result.connected_servers == 0
    assert result.loaded_tools == 0
