from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field


@dataclass
class ToolContext:
    cwd: str
    session_id: str


class ToolResult(BaseModel):
    ok: bool = True
    output: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ToolDef:
    name: str
    description: str
    params_model: type[BaseModel]
    permission: str
    pattern_from_args: Callable[[dict[str, Any]], str]
    execute: Callable[[BaseModel, ToolContext], Awaitable[ToolResult]]
    schema_override: dict[str, Any] | None = None

    def args_schema(self) -> dict[str, Any]:
        if self.schema_override is not None:
            return dict(self.schema_override)
        return self.params_model.model_json_schema()
