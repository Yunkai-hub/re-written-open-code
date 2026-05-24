from langchain_core.messages import HumanMessage

from opencode_py.agent.graph import _estimate_message_tokens, _estimate_message_tokens_fallback
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
