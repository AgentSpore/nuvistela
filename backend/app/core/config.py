from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Credits per text generation (docs.worldlabs.ai/api/pricing), 1 USD = 1250; no entry, no call.
WORLD3D_MODEL_CREDITS = {"marble-1.0-draft": 230, "marble-1.1": 1580}
WORLD3D_MICRO_USD_PER_CREDIT = 800


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str
    port: int = 8080
    # New families per UTC day, all callers; 0 = unlimited. 60 fits the daily cover and 3D budget.
    max_new_families_per_day: int = Field(default=60, ge=0)
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    cookie_secure: bool = True
    family_llm_model: str | None = None
    # Same model as the chapters; without OPENROUTER_API_KEY no world is generated, so a default
    # model alone never makes a paid call. Change the prices below together with it.
    # An override must support `reasoning`: the request sends it under require_parameters.
    world_model: str = "deepseek/deepseek-v4.1-flash"
    world_worker_enabled: bool = True
    world_max_attempts: int = Field(default=3, ge=1)
    world_retry_delay_s: float = Field(default=30.0, ge=0)
    world_poll_s: float = Field(default=0.5, gt=0)
    world_tokens_limit: int = 20_000
    # A model swap must re-check that it accepts `reasoning` (effort low) under require_parameters.
    chapter_model: str = "deepseek/deepseek-v4.1-flash"  # (Q-P2-1 default)
    # Room for a Russian chapter, summary and quest plus low-effort reasoning; reserved in full.
    chapter_max_tokens: int = Field(default=5500, ge=1)
    # USD per million tokens of each model, from OpenRouter /api/v1/models (2026-11-09). They
    # price the reservation and cap the request (provider max_price): change them with the model.
    chapter_price_in_usd_per_mtok: float = Field(default=0.051, ge=0)
    chapter_price_out_usd_per_mtok: float = Field(default=0.567, ge=0)
    world_max_tokens: int = Field(default=8000, ge=1)  # output ceiling of one world call
    world_price_in_usd_per_mtok: float = Field(default=0.051, ge=0)
    world_price_out_usd_per_mtok: float = Field(default=0.567, ge=0)
    # The chat agent: output ceiling of one model request and the price of FAMILY_LLM_MODEL, which
    # reserve and cap every request. Change the prices together with that model.
    chat_max_tokens: int = Field(default=1500, ge=1)
    chat_price_in_usd_per_mtok: float = Field(default=0.051, ge=0)
    chat_price_out_usd_per_mtok: float = Field(default=0.567, ge=0)
    llm_family_daily_cap_usd: float = Field(default=0.05, ge=0)  # (Q-P2-2 default), UTC day
    llm_global_daily_cap_usd: float = Field(default=2.0, ge=0)  # (Q-P2-2 default), UTC day
    # Paid image calls are capped apart from text: an image never uses up the text allowance.
    # 0.15 USD fits a first cover, one regeneration after the text check, and one growth cover in
    # a UTC day. Reserved worst case: about 0.047 (picture + 0.002 check) + 0.045 + 0.047 = 0.139;
    # settled, each picture costs about 0.034.
    image_family_daily_cap_usd: float = Field(default=0.15, ge=0)
    image_global_daily_cap_usd: float = Field(default=1.0, ge=0)  # UTC day
    # 3D worlds are capped apart again: one draft (~0.18 USD) costs more than the picture cap.
    # Empty model or no WORLDLABS_API_KEY = off: no scene job is queued and no scene worker runs.
    world3d_model: str = ""
    worldlabs_api_key: SecretStr | None = None
    world3d_poll_s: float = Field(default=10.0, gt=0)
    # Below the scene job lease (15 min).
    world3d_timeout_s: float = Field(default=600.0, gt=0, le=780)
    world3d_family_daily_cap_usd: float = Field(default=0.20, ge=0)  # one draft a day, UTC day
    world3d_global_daily_cap_usd: float = Field(default=3.0, ge=0)  # about 16 drafts, UTC day
    # The cover picture. Empty = off: no cover job is queued and no image worker runs, so no paid
    # image call can happen. The reserve is the ceiling per image plus the prompt bytes at the
    # input price; a measured model (google/gemini-3.1-flash-lite-image) costs 0.0336 USD.
    image_model: str = ""
    image_price_usd_per_image: float = Field(default=0.045, ge=0)
    image_price_in_usd_per_mtok: float = Field(default=0.1, ge=0)
    # USD per million tokens, sent as provider.max_price; a cap below the model's completion
    # (text) price gives 404 (not probed).
    # It does not bound this model's image_output price (probe 2026-11-14: completion=2 and
    # image=0.001 both returned 200 at 0.0336 USD). The per-image bound is the reserve
    # image_price_usd_per_image plus the worker halt on an actual cost above it.
    image_max_price_in_usd_per_mtok: float = Field(default=5, gt=0)
    image_max_price_out_usd_per_mtok: float = Field(default=200, gt=0)
    image_timeout_s: float = Field(default=30.0, gt=0)
    openrouter_api_key: SecretStr | None = None
    agent_request_limit: int = 10
    agent_total_tokens_limit: int = 30_000
    agent_family_daily_tokens: int = 200_000
    agent_history_limit: int = Field(default=40, ge=1)
    agent_max_text_chars: int = Field(default=2000, ge=1)
    agent_timeout_s: float = 60.0  # one chat turn (several model requests)
    # Whole-run deadline of one background call, from the latency measured on the real model
    # (150-165 completion tokens/s): a full 5500-token chapter takes ~37 s, a full 8000-token
    # world ~48 s. A chapter run is up to two requests (one output retry) sharing it, so 90 s;
    # it stays below the chapter job lease (5 min). Longer is a stuck call.
    chapter_timeout_s: float = Field(default=90.0, gt=0)
    # Flat pause before a failed chapter is tried again; a player watches "writing" meanwhile.
    chapter_retry_delay_s: float = Field(default=5.0, ge=0)
    world_timeout_s: float = Field(default=75.0, gt=0)
    telegram_bot_token: SecretStr | None = None
    # Derives share tokens (HMAC): lets a repeated request return the same link while the database
    # keeps only its hash. Unset = sharing refused. Changing it turns every sent link off.
    share_token_key: SecretStr | None = None
    telegram_webhook_secret: SecretStr | None = None
    telegram_webhook_url: str | None = None
    telegram_max_concurrent_updates: int = Field(default=8, ge=1)
    # Web Push (VAPID). All three set = reminders on; any unset = off. The key pair is created on
    # the stand: the private half only in the server env, the public half is served by the API.
    vapid_public_key: str | None = None
    vapid_private_key: SecretStr | None = None
    vapid_subject: str | None = None  # `mailto:` or `https:` contact the push services may use
    # Public origin; Telegram reminders link to `{site_url}/{locale}/adventure`.
    site_url: str | None = None
    reminder_poll_s: float = Field(default=300.0, gt=0)  # scan for "quest waiting" reminders
    reminder_window_start_hour: int = Field(default=17, ge=0, le=23)  # local, inclusive
    reminder_window_end_hour: int = Field(default=20, ge=1, le=24)  # local, exclusive

    @property
    def world3d_price_micro(self) -> int | None:
        """Micro-USD of one scene from the credit table; None for a model without a known price."""
        credits = WORLD3D_MODEL_CREDITS.get(self.world3d_model)
        return None if credits is None else credits * WORLD3D_MICRO_USD_PER_CREDIT

    @property
    def world3d_enabled(self) -> bool:
        """Key set and a known price that both daily caps can pay (else every scene is refused)."""
        price = self.world3d_price_micro
        caps = (self.world3d_family_daily_cap_usd, self.world3d_global_daily_cap_usd)
        cap = round(min(caps) * 1_000_000)
        return bool(self.worldlabs_api_key and price is not None and price <= cap)

    @property
    def push_enabled(self) -> bool:
        private = self.vapid_private_key.get_secret_value() if self.vapid_private_key else ""
        return bool(self.vapid_public_key and private and self.vapid_subject)

    @field_validator("share_token_key")
    @classmethod
    def _share_key_blank_means_off(cls, key: SecretStr | None) -> SecretStr | None:
        """`SHARE_TOKEN_KEY=` in an env file is unset, not an empty HMAC key."""
        value = key.get_secret_value().strip() if key is not None else ""
        if not value:
            return None
        if len(value) < 32:
            raise ValueError("share_token_key must be at least 32 characters")
        return SecretStr(value)  # padding in an env file must not change the HMAC key

    @model_validator(mode="after")
    def _history_covers_request_pairs(self) -> Self:
        """A turn stores a request and a reply per model call, so the window must fit them."""
        if self.agent_history_limit < 2 * self.agent_request_limit:
            raise ValueError("agent_history_limit must be >= 2 * agent_request_limit")
        return self

    @model_validator(mode="after")
    def _reminder_window_is_not_empty(self) -> Self:
        if self.reminder_window_start_hour >= self.reminder_window_end_hour:
            raise ValueError("reminder_window_start_hour must be < reminder_window_end_hour")
        return self
