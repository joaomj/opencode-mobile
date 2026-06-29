from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ENV_FILE = Path(".env")
DEFAULT_BRIDGE_DB_PATH = (
    Path.home() / ".local" / "state" / "opencode-telegram" / "bridge.db"
)


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
    opencode_request_timeout_seconds: float = 200.0
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    telegram_http_logs: bool = False
    log_file: str = "logs/opencode-telegram.log"
    log_max_bytes: int = 1048576
    log_backup_count: int = 7
    log_retention_days: int = 7
    bridge_db_path: str = str(DEFAULT_BRIDGE_DB_PATH)
    opencode_startup_retries: int = 5
    opencode_startup_retry_delay_seconds: float = 2.0

    model_config = SettingsConfigDict(
        env_file=DEFAULT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )
