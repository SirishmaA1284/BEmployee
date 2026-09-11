from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from environment variables / .env.

    See .env.example for the full documented list. Only variables actually
    consumed by code that exists today are declared here; later phases add
    more fields to this class as they introduce new configuration.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = (
        "postgresql+asyncpg://postgres:Chinki@localhost:5433/ai_employee"
    )

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # Phase 8: rotating refresh token lifetime (docs/security.md).
    refresh_token_expire_days: int = 30

    cors_origins: str = "http://localhost:5173"

    # --- Phase 9: distributed rate limiting (docs/security.md) ---
    # Redis URL for the shared rate-limit counters. Empty = in-process
    # (single-instance) limiter, which is what tests and local runs use.
    redis_url: str = ""

    # --- Phase 4: LLM provider (docs/decisions.md ADR-005) ---
    llm_provider: str = "mock"  # openai | anthropic | gemini | mock
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    # Cap on agent steps per chat request (NFR-3: no unbounded LLM loops).
    max_agent_steps: int = 10

    # --- Phase 6: proactive worker (docs/decisions.md ADR-007) ---
    scheduler_check_interval_minutes: int = 60
    scheduler_daily_report_hour: int = 8

    # --- Real messaging channels (optional; empty = mock fallback) ---
    # Telegram: token from @BotFather + chat id of the destination chat.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # WhatsApp Business Cloud API: Meta app access token, the sender's phone
    # number id, and the destination phone number (E.164, e.g. +9198...).
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_to_phone: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
