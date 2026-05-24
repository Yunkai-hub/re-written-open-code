from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    cwd: str
    agent: dict[str, Any]
    approved_ruleset: list[dict[str, str]]
    tokens: dict[str, int]
    step_count: int
    route: str
