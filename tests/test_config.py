import logging
from pathlib import Path

from opencode_telegram.bot import (
    CorrelationFormatter,
    DailySizeRotatingFileHandler,
    TokenMaskingFormatter,
    _build_log_path,
    _resolve_model_label,
)
from opencode_telegram.config import RuntimeConfig, load_settings
from opencode_telegram.session_state import ModelSelection

ALLOWED_USER_ID = 123
LOG_MAX_BYTES = 1_048_576
LOG_RETENTION_DAYS = 7


def test_load_settings_reads_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / "settings.env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=token\n"
        f"TELEGRAM_ALLOWED_USER_ID={ALLOWED_USER_ID}\n"
        "OPENCODE_BASE_URL=http://127.0.0.1:4096\n"
        "OPENCODE_SERVER_USERNAME=opencode\n"
        "OPENCODE_SERVER_PASSWORD=password\n",
        encoding="utf-8",
    )

    settings = load_settings(env_file=env_file)

    assert settings.telegram_bot_token == "token"
    assert settings.telegram_allowed_user_id == ALLOWED_USER_ID
    assert str(settings.opencode_base_url) == "http://127.0.0.1:4096/"
    assert settings.opencode_server_username == "opencode"
    assert settings.opencode_server_password == "password"


def test_runtime_config_has_streaming_controls() -> None:
    runtime = RuntimeConfig()

    assert runtime.telegram_edit_interval_seconds == 1.0
    assert runtime.opencode_event_logs is True
    assert not hasattr(runtime, "prompt_poll_interval_seconds")


def test_runtime_config_timeout_default_is_sixty() -> None:
    runtime = RuntimeConfig()

    assert runtime.opencode_request_timeout_seconds == 60.0


def test_token_masking_formatter() -> None:
    token = "123456:ABC-DEF_GHI"
    formatter = TokenMaskingFormatter(token=token)

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="got %s from api",
        args=(f"https://api.telegram.org/bot{token}/getMe",),
        exc_info=None,
    )

    result = formatter.format(record)

    assert token not in result
    assert "***" in result


def test_runtime_config_has_daily_log_rotation_defaults() -> None:
    runtime = RuntimeConfig()

    assert runtime.log_max_bytes == LOG_MAX_BYTES
    assert runtime.log_retention_days == LOG_RETENTION_DAYS


def test_build_log_path_uses_current_date() -> None:
    runtime = RuntimeConfig(log_file="logs/opencode-telegram.log")

    result = _build_log_path(runtime, date_text="2026-06-21")

    assert result == Path("logs/opencode-telegram-2026-06-21.log")


def test_daily_size_rotating_file_handler_uses_runtime_limits(tmp_path: Path) -> None:
    log_path = tmp_path / "opencode-telegram-2026-06-21.log"
    runtime = RuntimeConfig(log_max_bytes=LOG_MAX_BYTES, log_backup_count=LOG_RETENTION_DAYS)

    handler = DailySizeRotatingFileHandler(filename=str(log_path), runtime=runtime)
    try:
        assert handler.maxBytes == LOG_MAX_BYTES
        assert handler.backupCount == LOG_RETENTION_DAYS
    finally:
        handler.close()


def test_correlation_formatter_adds_correlation_id() -> None:
    formatter = CorrelationFormatter(fmt="cid=%(correlation_id)s %(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    result = formatter.format(record)

    assert result == "cid=- hello"


def test_resolve_model_label_shows_provider_and_model() -> None:
    label = _resolve_model_label(
        ModelSelection(providerID="openai", modelID="gpt-5.5")
    )

    assert label == "openai/gpt-5.5"


def test_resolve_model_label_shows_placeholder_when_none() -> None:
    label = _resolve_model_label(None)

    assert label == "—"
