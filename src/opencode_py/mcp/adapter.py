from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from opencode_py.mcp.client import MCPStdioClient, MCPToolInfo
from opencode_py.tools.base import ToolContext, ToolDef, ToolResult


class MCPParams(BaseModel):
    model_config = ConfigDict(extra="allow")


def _pattern_from_args(args: dict[str, Any]) -> str:
    return str(args.get("name", "*"))


def make_mcp_tooldef(server_name: str, tool: MCPToolInfo, client: MCPStdioClient) -> ToolDef:
    async def _execute(params: BaseModel, _ctx: ToolContext) -> ToolResult:
        payload = params.model_dump(exclude_none=True)
        result = await client.call_tool(tool.name, payload)
        content = result.get("content", [])
        if isinstance(content, list):
            text_blocks = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_blocks.append(str(block.get("text", "")))
            output = "\n".join([t for t in text_blocks if t]).strip() or str(result)
        else:
            output = str(result)
        return ToolResult(ok=True, output=output, metadata={"mcp_server": server_name, "mcp_tool": tool.name})

    return ToolDef(
        name=f"mcp.{server_name}.{tool.name}",
        description=tool.description or f"MCP tool {tool.name} from {server_name}",
        params_model=MCPParams,
        permission="mcp",
        pattern_from_args=_pattern_from_args,
        execute=_execute,  # type: ignore[arg-type]
        schema_override=tool.input_schema,
    )
