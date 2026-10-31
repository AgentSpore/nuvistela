from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    port: int = 8080
    family_llm_model: str | None = None
    openrouter_api_key: str | None = None
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
