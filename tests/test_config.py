from pathlib import Path

from opencode_telegram.config import load_settings

ALLOWED_USER_ID = 123


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
