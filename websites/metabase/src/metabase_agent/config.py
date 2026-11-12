"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MetabaseConfig(BaseSettings):
    """Metabase connection settings."""

    model_config = SettingsConfigDict(
        env_prefix="METABASE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "http://localhost:3000"
    username: str = "agent@example.com"
    password: str = "changeme"


class ModelConfig(BaseSettings):
    """LLM model settings for the agent.

    Supports multiple providers via LiteLLM naming convention:
    - OpenAI: "gpt-4", "gpt-4o", "gpt-4o-mini"
    - Gemini: "gemini/gemini-2.0-flash", "gemini/gemini-1.5-pro"
    - Azure: "azure/deployment-name"
    - OpenRouter: "openrouter/model-name"
    """

    model_config = SettingsConfigDict(
        env_prefix="MODEL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    name: str = "gemini/gemini-2.0-flash"
    api_key: str = ""
    base_url: str = ""


class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    metabase: MetabaseConfig = Field(default_factory=MetabaseConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)

    headless: bool = True
    artifacts_dir: Path = Path("./runs")
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> "AppConfig":
        """Load configuration from environment."""
        return cls(
            metabase=MetabaseConfig(),
            model=ModelConfig(),
        )
