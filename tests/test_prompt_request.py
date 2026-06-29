from unittest.mock import AsyncMock

import pytest

from opencode_telegram.config import RuntimeConfig, Settings
from opencode_telegram.opencode_client import OpencodeClient


def _fake_settings() -> Settings:
    return Settings(
        telegram_bot_token="token",
        telegram_allowed_user_id=1,
        opencode_base_url="http://127.0.0.1:4096",
        opencode_server_username="opencode",
        opencode_server_password="password",
    )


@pytest.fixture
def client_with_captured_post() -> tuple[OpencodeClient, AsyncMock]:
    client = OpencodeClient(
        settings=_fake_settings(),
        runtime=RuntimeConfig(),
    )
    mock_post = AsyncMock()
    mock_post.return_value.raise_for_status = lambda: None
    mock_post.return_value.status_code = 204
    client._client.post = mock_post
    return client, mock_post


@pytest.mark.asyncio
async def test_prompt_async_body_excludes_response_only_fields(
    client_with_captured_post: tuple[OpencodeClient, AsyncMock],
) -> None:
    client, mock_post = client_with_captured_post

    await client.send_prompt_async(
        session_id="ses_123",
        text="hello world",
    )

    assert mock_post.call_count == 1
    _path, kwargs = mock_post.call_args
    body = kwargs["json"]

    assert "parts" in body
    part = body["parts"][0]
    assert part["type"] == "text"
    assert part["text"] == "hello world"
    assert "sessionID" not in part
    assert "messageID" not in part
    assert "session_id" not in part
    assert "message_id" not in part


@pytest.mark.asyncio
async def test_prompt_async_body_excludes_empty_id(
    client_with_captured_post: tuple[OpencodeClient, AsyncMock],
) -> None:
    client, mock_post = client_with_captured_post

    await client.send_prompt_async(
        session_id="ses_123",
        text="hello world",
    )

    _path, kwargs = mock_post.call_args
    body = kwargs["json"]

    part = body["parts"][0]
    assert "id" not in part
