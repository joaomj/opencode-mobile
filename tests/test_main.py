import pytest
from pydantic import ValidationError

from opencode_telegram import format_startup_error
from opencode_telegram.config import Settings


def test_format_startup_error_names_invalid_settings_without_values() -> None:
    with pytest.raises(ValidationError) as exc_info:
        raise_settings_error()

    message = format_startup_error(exc_info.value)

    assert "Invalid configuration" in message
    assert "opencode_server_username" in message
    assert "opencode_server_password" in message
    assert "token" not in message


def raise_settings_error() -> None:
    Settings(
        telegram_bot_token="token",
        telegram_allowed_user_id=123,
        opencode_base_url="http://127.0.0.1:4096",
        opencode_server_username="",
        opencode_server_password="",
    )
