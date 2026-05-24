from __future__ import annotations

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from opencode_py.config import Settings
from opencode_py.session.models import AgentConfig


def build_chat_model(agent: AgentConfig, settings: Settings):
    provider = settings.provider.lower().strip()
    temperature = agent.temperature if agent.temperature is not None else 1.0

    if provider == "anthropic":
        api_key = settings.anthropic_api_key
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set. Set it in env or .env")
        return ChatAnthropic(
            model_name=agent.model,
            api_key=api_key,
            base_url=settings.anthropic_base_url,
            temperature=temperature,
            timeout=120,
        )

    if provider == "openai":
        api_key = settings.openai_api_key
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set. Set it in env or .env")
        return ChatOpenAI(
            model=agent.model,
            api_key=api_key,
            base_url=settings.openai_base_url,
            temperature=temperature,
            timeout=120,
        )

    raise ValueError(f"Unsupported provider: {settings.provider}. Expected one of: anthropic, openai")
