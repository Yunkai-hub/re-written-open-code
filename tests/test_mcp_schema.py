from opencode_py.mcp.schema import MCPConfig, MCPServerConfig


def test_mcp_schema_accepts_stdio_server():
    cfg = MCPConfig(
        servers={
            "fs": MCPServerConfig(
                transport="stdio",
                command="python",
                args=["-m", "x"],
            )
        }
    )
    assert "fs" in cfg.servers


def test_mcp_schema_rejects_missing_stdio_command():
    try:
        MCPServerConfig(transport="stdio")
    except Exception as exc:
        assert "command" in str(exc)
    else:
        raise AssertionError("expected validation failure")
