from __future__ import annotations

import time
import uuid
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    id: str = Field(default_factory=lambda: _new_id("prt"))
    text: str = ""


class ReasoningPart(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    id: str = Field(default_factory=lambda: _new_id("prt"))
    text: str = ""


class ToolCallPart(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str = Field(default_factory=lambda: _new_id("prt"))
    call_id: str
    tool: str
    args: dict[str, Any]
    status: Literal["pending", "approved", "denied", "running", "ok", "error", "interrupted"] = "pending"


class ToolResultPart(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    id: str = Field(default_factory=lambda: _new_id("prt"))
    call_id: str
    tool: str
    ok: bool
    output: str
    metadata: dict[str, Any] = Field(default_factory=dict)


Part = Annotated[
    TextPart | ReasoningPart | ToolCallPart | ToolResultPart,
    Field(discriminator="type"),
]


class Message(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("msg"))
    role: Literal["user", "assistant", "system", "tool"]
    parts: list[Part] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)

    def text(self) -> str:
        return "".join(p.text for p in self.parts if isinstance(p, TextPart))


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0


class AgentConfig(BaseModel):
    name: str = "default"
    model: str = "claude-sonnet-4-5-20250929"
    temperature: float | None = None
    system_prompt: str = (
        "You are opencode-py, an interactive coding assistant. "
        "Use the provided tools to inspect and modify the user's project. "
        "Prefer concrete actions over speculation. Keep responses brief."
    )
    max_steps: int = 25
