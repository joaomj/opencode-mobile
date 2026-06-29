from unittest.mock import AsyncMock

import httpx
import pytest

from opencode_telegram.bot import load_opencode_commands_resilient
from opencode_telegram.config import RuntimeConfig, Settings
from opencode_telegram.opencode_client import Command, OpencodeClient


def _settings_kwargs() -> dict[str, object]:
    return {
        "telegram_bot_token": "token",
        "telegram_allowed_user_id": 1,
        "opencode_base_url": "http://127.0.0.1:4096",
        "opencode_server_password": "pw",
    }


def _client_with_retries(runtime: RuntimeConfig, fail_count: int) -> OpencodeClient:
    client = OpencodeClient(
        settings=Settings(**_settings_kwargs()),
        runtime=runtime,
    )
    attempts = {"n": 0}

    async def side_effect() -> list[Command]:
        attempts["n"] += 1
        if attempts["n"] <= fail_count:
            raise httpx.ConnectError("server unreachable")
        return [Command(name="commit", description="commit changes")]

    client.list_commands = AsyncMock(side_effect=side_effect)  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_load_commands_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = RuntimeConfig(
        opencode_startup_retries=3,
        opencode_startup_retry_delay_seconds=0.0,
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    client = _client_with_retries(runtime, fail_count=2)

    commands = await load_opencode_commands_resilient(client=client, runtime=runtime)

    assert len(commands) == 1
    assert commands[0].name == "commit"
    await client.close()


@pytest.mark.asyncio
async def test_load_commands_returns_empty_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RuntimeConfig(
        opencode_startup_retries=2,
        opencode_startup_retry_delay_seconds=0.0,
    )
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    client = OpencodeClient(
        settings=Settings(**_settings_kwargs()),
        runtime=runtime,
    )
    client.list_commands = AsyncMock(side_effect=httpx.ConnectError("nope"))  # type: ignore[method-assign]
    commands = await load_opencode_commands_resilient(client=client, runtime=runtime)

    assert commands == []
    assert client.list_commands.call_count == 2
    assert sleep_calls == [0.0]
    await client.close()


@pytest.mark.asyncio
async def test_on_unavailable_callback_invoked_when_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RuntimeConfig(
        opencode_startup_retries=1,
        opencode_startup_retry_delay_seconds=0.0,
    )
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    client = OpencodeClient(
        settings=Settings(**_settings_kwargs()),
        runtime=runtime,
    )
    client.list_commands = AsyncMock(side_effect=httpx.ConnectError("nope"))  # type: ignore[method-assign]
    invoked: list[str] = []

    async def on_unavailable() -> None:
        invoked.append("called")

    await load_opencode_commands_resilient(
        client=client, runtime=runtime, on_unavailable=on_unavailable
    )

    assert invoked == ["called"]
    await client.close()


@pytest.mark.asyncio
async def test_load_commands_no_retry_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RuntimeConfig(opencode_startup_retries=5)
    monkeypatch.setattr("asyncio.sleep", AsyncMock(return_value=None))
    client = OpencodeClient(
        settings=Settings(**_settings_kwargs()),
        runtime=runtime,
    )
    client.list_commands = AsyncMock(return_value=[Command(name="new")])  # type: ignore[method-assign]

    commands = await load_opencode_commands_resilient(client=client, runtime=runtime)

    assert len(commands) == 1
    assert client.list_commands.call_count == 1
    await client.close()
