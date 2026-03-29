from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Stock Bot"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "development"
    log_level: str = "INFO"
    enable_scheduler: bool = True

    gemini_api_key: str = ""
    gemini_api_key_2: str = ""
    gemini_api_key_3: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_batch_size: int = Field(default=5, ge=1, le=5)

    nse_index_name: str = "NIFTY TOTAL MARKET"
    lookback_days: int = 370
    filter_near_wkl_pct: float = 5.0
    bucket_1_near_wkl_pct: float = 5.0
    bucket_2_near_wkl_pct: float = 10.0
    bucket_3_near_wkl_pct: float = 20.0
    filter_max_pe: float = 25.0
    filter_max_pb: float = 3.0
    filter_max_debt_to_equity: float = 1.0
    filter_max_30d_change: float = -0.01

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""
    twilio_to: str = ""

    schedule_hour: int = Field(default=8, ge=0, le=23)
    schedule_minute: int = Field(default=30, ge=0, le=59)

    prompts_dir: Path = BASE_DIR / "prompts"
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"

    @property
    def gemini_api_keys(self) -> list[str]:
        return [key for key in [self.gemini_api_key, self.gemini_api_key_2, self.gemini_api_key_3] if key]


@lru_cache
def get_settings() -> Settings:
    return Settings()
