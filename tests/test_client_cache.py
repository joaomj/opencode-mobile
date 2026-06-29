from unittest.mock import AsyncMock, MagicMock

import pytest

from opencode_telegram.config import RuntimeConfig, Settings
from opencode_telegram.opencode_client import OpencodeClient

_SINGLE_CALL = 1
_TWO_CALLS = 2


def _fake_settings() -> Settings:
    return Settings(
        telegram_bot_token="token",
        telegram_allowed_user_id=1,
        opencode_base_url="http://127.0.0.1:4096",
        opencode_server_username="opencode",
        opencode_server_password="password",
    )


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def __call__(self) -> float:
        return self._now


@pytest.fixture
def cached_client() -> tuple[OpencodeClient, FakeClock, AsyncMock]:
    clock = FakeClock()
    client = OpencodeClient(
        settings=_fake_settings(),
        runtime=RuntimeConfig(),
        cache_ttl_seconds=60.0,
        clock=clock,
    )
    mock_get = AsyncMock()
    mock_get.return_value.raise_for_status = lambda: None
    mock_get.return_value.json = MagicMock(
        return_value=[{"name": "plan", "description": "Plan mode"}]
    )
    client._client.get = mock_get
    return client, clock, mock_get


@pytest.mark.asyncio
async def test_list_commands_cached_within_ttl(
    cached_client: tuple[OpencodeClient, FakeClock, AsyncMock],
) -> None:
    client, _clock, mock_get = cached_client

    result1 = await client.list_commands()
    result2 = await client.list_commands()

    assert mock_get.call_count == _SINGLE_CALL
    assert len(result1) == _SINGLE_CALL
    assert result1[0].name == "plan"
    assert result1 == result2


@pytest.mark.asyncio
async def test_list_commands_refreshed_after_ttl(
    cached_client: tuple[OpencodeClient, FakeClock, AsyncMock],
) -> None:
    client, _clock, mock_get = cached_client

    await client.list_commands()
    _clock.advance(61.0)
    await client.list_commands()

    assert mock_get.call_count == _TWO_CALLS


@pytest.mark.asyncio
async def test_list_agents_cached_within_ttl(
    cached_client: tuple[OpencodeClient, FakeClock, AsyncMock],
) -> None:
    client, _clock, mock_get = cached_client
    mock_get.return_value.json.return_value = [
        {"name": "build", "description": "Builder", "mode": "primary"}
    ]

    await client.list_agents()
    await client.list_agents()

    assert mock_get.call_count == _SINGLE_CALL


@pytest.mark.asyncio
async def test_different_cache_keys_are_independent(
    cached_client: tuple[OpencodeClient, FakeClock, AsyncMock],
) -> None:
    client, _clock, mock_get = cached_client
    mock_get.return_value.json.side_effect = [
        [{"name": "plan", "description": ""}],
        [{"name": "build", "description": "", "mode": "primary"}],
    ]

    await client.list_commands()
    await client.list_agents()

    assert mock_get.call_count == _TWO_CALLS
