from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MCPServerConfig(BaseModel):
    enabled: bool = True
    transport: Literal["stdio", "sse"] = "stdio"
    timeout_ms: int = Field(default=15_000, ge=100, le=600_000)

    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None

    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> "MCPServerConfig":
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("stdio transport requires command")
        elif self.transport == "sse":
            if not self.url:
                raise ValueError("sse transport requires url")
        return self


class MCPConfig(BaseModel):
    version: int = 1
    servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
