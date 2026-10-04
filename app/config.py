"""Central configuration, loaded from environment (and optional .env).

All settings are read from env vars so no secret ever lives in code. The defaults
make the project run fully offline in `mock` mode with a local SQLite file.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    llm_provider: str = Field(default="mock")  # mock | openai | anthropic | ollama
    llm_model: str = Field(default="")

    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="https://api.openai.com/v1")

    anthropic_api_key: str = Field(default="")

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_timeout: float = Field(default=600.0)       # seconds; CPU inference is slow
    ollama_keep_alive: str = Field(default="30m")      # keep model resident between calls
    ollama_num_ctx: int = Field(default=8192)          # avoid overflowing the 4096 default

    # Database
    freight_db_path: str = Field(default="data/freight.db")

    # Tracing
    langfuse_enabled: bool = Field(default=False)
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    def resolved_model(self) -> str:
        """Return a sensible default model name per provider if none configured."""
        if self.llm_model:
            return self.llm_model
        return {
            "openai": "gpt-4o-mini",
            "anthropic": "claude-sonnet-4-6",
            "ollama": "llama3.1",
            "mock": "mock",
        }.get(self.llm_provider, "mock")


@lru_cache
def get_settings() -> Settings:
    return Settings()
