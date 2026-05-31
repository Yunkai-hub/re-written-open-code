from langchain_core.messages import HumanMessage

from opencode_py.agent.graph import (
    _estimate_message_tokens,
    _estimate_message_tokens_fallback,
    _estimate_message_tokens_with_source,
    _estimate_payload_tokens_with_source,
)
from opencode_py.config import settings


def test_estimate_message_tokens_grows_with_text_length():
    short = [HumanMessage(content="hello")]
    long = [HumanMessage(content="hello " * 1000)]
    assert _estimate_message_tokens(long) > _estimate_message_tokens(short)


def test_estimate_message_tokens_fallback_grows_with_text_length():
    short = [HumanMessage(content="hello")]
    long = [HumanMessage(content="hello " * 1000)]
    assert _estimate_message_tokens_fallback(long) > _estimate_message_tokens_fallback(short)


def test_compaction_trigger_tokens_is_positive():
    assert settings.compaction_trigger_tokens() > 0
    assert settings.usable_context_tokens() > 0


def test_estimate_message_tokens_with_source_has_valid_source():
    short = [HumanMessage(content="hello")]
    estimated, source = _estimate_message_tokens_with_source(short)
    assert estimated > 0
    assert source in {"provider", "model_api", "fallback"}


def test_estimate_payload_tokens_with_source_includes_tool_overhead():
    short = [HumanMessage(content="hello")]
    estimated_without_tools, _ = _estimate_payload_tokens_with_source(short, include_tools=False)
    estimated_with_tools, _ = _estimate_payload_tokens_with_source(short, include_tools=True)
    assert estimated_with_tools >= estimated_without_tools
