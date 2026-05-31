from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

from opencode_py.mcp.schema import MCPServerConfig


@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict


class MCPStdioClient:
    def __init__(self, server_name: str, cfg: MCPServerConfig):
        self.server_name = server_name
        self.cfg = cfg
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 1

    async def start(self) -> None:
        if self.proc is not None:
            return
        env = os.environ.copy()
        env.update(self.cfg.env)
        self.proc = await asyncio.create_subprocess_exec(
            self.cfg.command or "",
            *self.cfg.args,
            cwd=self.cfg.cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "opencode-py", "version": "0.1.0"}})

    async def stop(self) -> None:
        if self.proc is None:
            return
        if self.proc.stdin and not self.proc.stdin.is_closing():
            self.proc.stdin.close()
        self.proc.terminate()
        await self.proc.wait()
        self.proc = None

    async def list_tools(self) -> list[MCPToolInfo]:
        result = await self._request("tools/list", {})
        tools = result.get("tools", [])
        out: list[MCPToolInfo] = []
        for t in tools:
            out.append(
                MCPToolInfo(
                    name=str(t.get("name", "")),
                    description=str(t.get("description", "")),
                    input_schema=t.get("inputSchema") or {"type": "object", "properties": {}},
                )
            )
        return out

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        return await self._request("tools/call", {"name": tool_name, "arguments": arguments})

    async def _request(self, method: str, params: dict) -> dict:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("MCP stdio client is not started")

        req_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        msg = json.dumps(payload, ensure_ascii=False) + "\n"
        self.proc.stdin.write(msg.encode("utf-8"))
        await self.proc.stdin.drain()

        timeout = self.cfg.timeout_ms / 1000
        line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=timeout)
        if not line:
            raise RuntimeError("MCP server closed stdout")
        resp = json.loads(line.decode("utf-8", errors="replace"))
        if "error" in resp:
            raise RuntimeError(f"MCP error: {resp['error']}")
        result = resp.get("result")
        if not isinstance(result, dict):
            return {}
        return result
