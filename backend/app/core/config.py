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

    cors_origins: str = "http://localhost:5173"

    # --- Phase 4: LLM provider (docs/decisions.md ADR-005) ---
    llm_provider: str = "mock"  # openai | anthropic | gemini | mock
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Cap on agent steps per chat request (NFR-3: no unbounded LLM loops).
    max_agent_steps: int = 10

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
