from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    port: int = 8080
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    cookie_secure: bool = True
    family_llm_model: str | None = None
    world_model: str | None = None
    world_worker_enabled: bool = True
    world_max_attempts: int = Field(default=3, ge=1)
    world_retry_delay_s: float = Field(default=30.0, ge=0)
    world_poll_s: float = Field(default=2.0, gt=0)
    world_tokens_limit: int = 20_000
    openrouter_api_key: SecretStr | None = None
    agent_request_limit: int = 10
    agent_total_tokens_limit: int = 30_000
    agent_family_daily_tokens: int = 200_000
    agent_history_limit: int = Field(default=40, ge=1)
    agent_max_text_chars: int = Field(default=2000, ge=1)
    agent_timeout_s: float = 60.0
    telegram_bot_token: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_webhook_url: str | None = None
    telegram_max_concurrent_updates: int = Field(default=8, ge=1)

    @model_validator(mode="after")
    def _history_covers_request_pairs(self) -> Self:
        """A turn stores a request and a reply per model call, so the window must fit them."""
        if self.agent_history_limit < 2 * self.agent_request_limit:
            raise ValueError("agent_history_limit must be >= 2 * agent_request_limit")
        return self
