"""Application settings loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FarmShield AI"
    environment: str = "development"
    database_url: str = "sqlite:///./farmshield.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Weather data
    weather_provider: str = "mock"  # mock | conduit
    conduit_api_url: str = ""
    conduit_api_key: str = ""
    default_scenario: str = "normal"  # normal | dry_spell | heavy_rain

    # Advice generation (Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    # SMS (Africa's Talking sandbox)
    at_username: str = "sandbox"
    at_api_key: str = ""
    at_sender_id: str = ""
    sms_sender: str = "console"  # console | africastalking

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
