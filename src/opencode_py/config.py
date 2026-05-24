from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENCODE_", env_file=".env", extra="ignore")

    provider: str = "anthropic"
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    anthropic_base_url: str | None = Field(default=None, validation_alias="OPENCODE_ANTHROPIC_BASE_URL")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENCODE_OPENAI_BASE_URL")
    model: str = "claude-sonnet-4-5-20250929"
    max_steps: int = 25
    data_dir: Path = Path.home() / ".opencode-py"

    def session_db_path(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "sessions.sqlite"


settings = Settings()
