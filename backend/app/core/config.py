from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    port: int = 8080
    cookie_secure: bool = True
    family_llm_model: str | None = None
    openrouter_api_key: SecretStr | None = None
    agent_request_limit: int = 10
    agent_total_tokens_limit: int = 30_000
    agent_family_daily_tokens: int = 200_000
    agent_history_limit: int = 40
    agent_timeout_s: float = 60.0
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
