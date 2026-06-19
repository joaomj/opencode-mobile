from opencode_telegram.bot import is_allowed_user
from opencode_telegram.config import Settings


def test_allowed_user_is_processed() -> None:
    settings = Settings(
        telegram_bot_token="token",
        telegram_allowed_user_id=123,
        opencode_base_url="http://127.0.0.1:4096",
        opencode_server_username="user",
        opencode_server_password="password",
    )

    assert is_allowed_user(user_id=123, settings=settings)


def test_unlisted_user_is_ignored() -> None:
    settings = Settings(
        telegram_bot_token="token",
        telegram_allowed_user_id=123,
        opencode_base_url="http://127.0.0.1:4096",
        opencode_server_username="user",
        opencode_server_password="password",
    )

    assert not is_allowed_user(user_id=999, settings=settings)
