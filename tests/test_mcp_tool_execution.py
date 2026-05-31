import pytest

from opencode_py.mcp.adapter import MCPParams, make_mcp_tooldef
from opencode_py.mcp.client import MCPToolInfo
from opencode_py.tools.base import ToolContext


class _DummyClient:
    async def call_tool(self, tool_name: str, arguments: dict):
        return {
            "content": [
                {"type": "text", "text": f"tool={tool_name}"},
                {"type": "text", "text": f"args={arguments}"},
            ]
        }


@pytest.mark.asyncio
async def test_mcp_tooldef_execute_returns_text_output():
    info = MCPToolInfo(name="echo", description="Echo", input_schema={"type": "object", "properties": {"text": {"type": "string"}}})
    td = make_mcp_tooldef("demo", info, _DummyClient())  # type: ignore[arg-type]

    params = MCPParams.model_validate({"text": "hello"})
    ctx = ToolContext(cwd=".", session_id="s")
    out = await td.execute(params, ctx)
    assert out.ok is True
    assert "tool=echo" in out.output
