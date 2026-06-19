from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = Path(".env")


class Settings(BaseSettings):
    telegram_bot_token: str = Field(min_length=1)
    telegram_allowed_user_id: int
    opencode_base_url: AnyHttpUrl
    opencode_server_username: str = Field(default="opencode", min_length=1)
    opencode_server_password: str = Field(min_length=1)

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


def load_settings(env_file: Path = DEFAULT_ENV_FILE) -> Settings:
    return Settings(_env_file=env_file)  # type: ignore[call-arg]


class RuntimeConfig(BaseSettings):
    telegram_message_limit: int = 4096
    opencode_request_timeout_seconds: float = 120.0
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    opencode_event_logs: bool = True
    telegram_http_logs: bool = False
    log_file: str = "logs/opencode-telegram.log"
    log_max_bytes: int = 5242880
    log_backup_count: int = 1
    prompt_poll_interval_seconds: float = 2.0

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )
