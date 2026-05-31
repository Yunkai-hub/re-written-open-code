from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from opencode_py.config import settings
from opencode_py.mcp.adapter import make_mcp_tooldef
from opencode_py.mcp.client import MCPStdioClient
from opencode_py.mcp.loader import load_mcp_config
from opencode_py.mcp.schema import MCPConfig
from opencode_py.tools import registry


@dataclass
class MCPBootstrapResult:
    enabled: bool
    configured_servers: int = 0
    connected_servers: int = 0
    loaded_tools: int = 0
    errors: list[str] = field(default_factory=list)


class MCPManager:
    def __init__(self):
        self.clients: dict[str, MCPStdioClient] = {}

    async def bootstrap(self) -> MCPBootstrapResult:
        await self.shutdown()
        if not settings.mcp_enabled or not settings.mcp_config_path:
            registry.clear_dynamic()
            return MCPBootstrapResult(enabled=False)

        result = MCPBootstrapResult(enabled=True)
        registry.clear_dynamic()

        config: MCPConfig
        try:
            config = load_mcp_config(settings.mcp_config_path)
        except Exception as exc:
            msg = f"mcp config load failed: {exc}"
            if settings.mcp_startup_strict:
                raise RuntimeError(msg) from exc
            return MCPBootstrapResult(enabled=True, errors=[msg])

        result.configured_servers = len(config.servers)

        for name, cfg in config.servers.items():
            if not cfg.enabled:
                continue
            if cfg.transport != "stdio":
                result.errors.append(f"server {name}: transport {cfg.transport} not supported in Phase 5A")
                continue

            client = MCPStdioClient(name, cfg)
            try:
                await client.start()
                tools = await client.list_tools()
            except Exception as exc:
                err = f"server {name} bootstrap failed: {exc}"
                if settings.mcp_startup_strict:
                    raise RuntimeError(err) from exc
                result.errors.append(err)
                continue

            self.clients[name] = client
            result.connected_servers += 1
            defs = [make_mcp_tooldef(name, t, client) for t in tools]
            registry.register_many(defs, dynamic=True)
            result.loaded_tools += len(defs)

        return result

    async def shutdown(self) -> None:
        for c in self.clients.values():
            try:
                await c.stop()
            except Exception:
                pass
        self.clients.clear()


_manager_singleton: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    global _manager_singleton
    if _manager_singleton is None:
        _manager_singleton = MCPManager()
    return _manager_singleton


def bootstrap_mcp_sync() -> MCPBootstrapResult:
    return asyncio.run(get_mcp_manager().bootstrap())
