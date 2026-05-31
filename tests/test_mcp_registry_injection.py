from opencode_py.mcp.adapter import make_mcp_tooldef
from opencode_py.mcp.client import MCPToolInfo
from opencode_py.tools import registry


class _DummyClient:
    async def call_tool(self, tool_name: str, arguments: dict):
        return {"content": [{"type": "text", "text": f"ok:{tool_name}"}]}


def test_registry_can_register_dynamic_mcp_tool():
    registry.clear_dynamic()
    t = MCPToolInfo(name="search", description="search tool", input_schema={"type": "object", "properties": {}})
    td = make_mcp_tooldef("demo", t, _DummyClient())  # type: ignore[arg-type]
    registry.register(td, dynamic=True)

    got = registry.get("mcp.demo.search")
    assert got is not None
    assert got.permission == "mcp"

    registry.clear_dynamic()
