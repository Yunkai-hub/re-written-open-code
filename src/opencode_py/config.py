from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPENCODE_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    provider: str = "anthropic"
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_base_url: str | None = Field(default=None, validation_alias="OPENCODE_ANTHROPIC_BASE_URL")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENCODE_OPENAI_BASE_URL")

    model: str = "claude-sonnet-4-5-20250929"
    max_steps: int = 25

    context_window_tokens: int = 200_000
    compaction_enabled: bool = True
    compaction_trigger_ratio: float = 0.85
    compaction_reserved_tokens: int = 12_000
    compaction_tail_turns: int = 2
    compaction_max_summary_chars: int = 6_000
    compaction_token_counter: Literal["auto", "provider", "model_api", "fallback"] = "auto"

    data_dir: Path = Path.home() / ".opencode-py"

    def session_db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "sessions.sqlite"

    def usable_context_tokens(self) -> int:
        return max(1, self.context_window_tokens - self.compaction_reserved_tokens)

    def compaction_trigger_tokens(self) -> int:
        return max(1, int(self.context_window_tokens * self.compaction_trigger_ratio))


settings = Settings()
