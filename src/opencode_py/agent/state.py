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
    estimated_payload_tokens: int
    estimated_tokens: int
    token_counter_source: str
    runtime_ctx_calibration_ratio: float
    overflow: bool
    overflow_reason: str
    compaction_visible_tokens_before: int
    compaction_visible_tokens_after: int
    compaction_last_ratio: float
    compaction_trigger_count: int
    last_compacted_at: float
    force_compact: bool
    compact_only: bool
    visible_start_index: int
    compaction_count: int
    last_compaction_summary: str | None

    step_count: int
    route: str
