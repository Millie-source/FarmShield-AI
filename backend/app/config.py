"""Application settings loaded from environment / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FarmShield AI"
    environment: str = "development"
    database_url: str = "sqlite:///./farmshield.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Weather data: conduit_api (live Conduit@Empathy API) | conduit_csv (station export, default) | scenario (synthetic demo)
    weather_provider: str = "conduit_csv"
    conduit_api_url: str = "https://conduit.jhubafrica.com/data.php"
    conduit_api_key: str = ""  # never logged
    conduit_email: str = ""  # never logged
    conduit_daily_csv: str = "data/conduit_daily.csv"  # relative to backend/
    conduit_raw_csv: str = "data/conduit_raw.csv"  # GeoCSV export; ingested to the daily file if present
    conduit_cache_dir: str = "data/cache"
    conduit_cache_ttl_min: int = 15  # for windows that include today; past windows are cached forever
    default_scenario: str = "normal"  # normal | dry_spell | heavy_rain (synthetic demo + backfill padding)

    # Advice generation (Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    # SMS (Africa's Talking sandbox)
    at_username: str = "sandbox"
    at_api_key: str = ""
    at_sender_id: str = ""
    sms_sender: str = "console"  # console | africastalking

    # Alerts: when a new assessment warrants an SMS and how aggressively to dedupe
    alert_min_level: str = "MEDIUM"  # LOW | MEDIUM | HIGH - lowest overall level that triggers an alert
    alert_dedupe_hours: int = 6  # no repeat SMS within this window unless the level changes

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
