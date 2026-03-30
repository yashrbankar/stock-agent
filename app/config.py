from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

    nse_index_names: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "NIFTY 100",
            "NIFTY MIDCAP 100",
            "NIFTY SMALLCAP 100",
        ],
        validation_alias=AliasChoices("NSE_INDEX_NAMES", "NSE_INDEX_NAME"),
    )
    near_52_week_low_pct: float = 5.0
    segment_top_n: int = Field(default=20, ge=1, le=50)

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

    schedule_hour: int = Field(default=4, ge=0, le=23)
    schedule_minute: int = Field(default=0, ge=0, le=59)

    prompts_dir: Path = BASE_DIR / "prompts"
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"

    @property
    def gemini_api_keys(self) -> list[str]:
        keys: list[str] = []
        for value in [self.gemini_api_key, self.gemini_api_key_2, self.gemini_api_key_3]:
            if not value:
                continue
            keys.extend([item.strip() for item in value.split(",") if item.strip()])
        return keys

    @field_validator("nse_index_names", mode="before")
    @classmethod
    def _parse_nse_index_names(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def nse_universe_label(self) -> str:
        return ", ".join(self.nse_index_names)


@lru_cache
def get_settings() -> Settings:
    return Settings()
