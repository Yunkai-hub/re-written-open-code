from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    cwd: str
    session_id: str
    fork_parent_thread_id: str | None

    agent: dict[str, Any]
    approved_ruleset: list[dict[str, str]]

    tokens: dict[str, int]
    estimated_tokens: int
    overflow: bool
    force_compact: bool
    compact_only: bool
    visible_start_index: int
    compaction_count: int
    last_compaction_summary: str | None

    step_count: int
    route: str
