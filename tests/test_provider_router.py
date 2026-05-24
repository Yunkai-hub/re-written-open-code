import pytest

from opencode_py.config import Settings
from opencode_py.providers.router import build_chat_model
from opencode_py.session.models import AgentConfig


def test_router_requires_anthropic_key():
    settings = Settings(
        provider="anthropic",
        anthropic_api_key="",
        openai_api_key="",
        model="claude-sonnet-4-5-20250929",
        max_steps=3,
    )
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_chat_model(AgentConfig(), settings)


def test_router_requires_openai_key():
    settings = Settings(
        provider="openai",
        anthropic_api_key="",
        openai_api_key="",
        model="gpt-4o-mini",
        max_steps=3,
    )
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_chat_model(AgentConfig(model="gpt-4o-mini"), settings)


def test_router_rejects_unknown_provider():
    settings = Settings(provider="unknown", anthropic_api_key="x", openai_api_key="x")
    with pytest.raises(ValueError, match="Unsupported provider"):
        build_chat_model(AgentConfig(), settings)
