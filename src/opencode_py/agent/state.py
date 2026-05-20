from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from opencode_py.permission.schema import Ruleset
from opencode_py.session.models import AgentConfig, TokenUsage


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    cwd: str
    agent: AgentConfig
    approved_ruleset: Ruleset
    tokens: TokenUsage
    step_count: int
