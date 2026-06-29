import logging
import time
from collections.abc import Callable
from typing import Any, cast

import httpx

from opencode_telegram.config import RuntimeConfig, Settings
from opencode_telegram.models import (
    Command,
    CommandRequest,
    Message,
    MessageRequest,
    PermissionReplyRequest,
    PermissionRequest,
    Session,
    TextPartInput,
)

LOGGER = logging.getLogger(__name__)


class OpencodeClient:
    def __init__(
        self,
        settings: Settings,
        runtime: RuntimeConfig | None = None,
        cache_ttl_seconds: float | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._settings = settings
        self._runtime = runtime or RuntimeConfig()
        self._clock = clock or time.monotonic
        timeout = self._runtime.opencode_request_timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=str(settings.opencode_base_url),
            auth=(settings.opencode_server_username, settings.opencode_server_password),
            timeout=timeout,
            limits=httpx.Limits(
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, dict[str, Any]] = {}

    async def close(self) -> None:
        await self._client.aclose()

    async def list_commands(self) -> list[Command]:
        if self._cache_ttl_seconds is not None:
            cached = self._get_cache("/command")
            if cached is not None:
                return cast(list[Command], cached)
        response = await self._client.get("/command")
        response.raise_for_status()
        result = [Command.model_validate(item) for item in response.json()]
        self._set_cache("/command", result)
        return result

    async def list_sessions(self) -> list[Session]:
        response = await self._client.get("/session")
        response.raise_for_status()
        return [Session.model_validate(item) for item in response.json()]

    async def create_session(self, title: str | None = None) -> Session:
        body = {"title": title} if title is not None else None
        response = await self._client.post("/session", json=body)
        response.raise_for_status()
        return Session.model_validate(response.json())

    async def send_message(self, session_id: str, text: str) -> Message:
        request = MessageRequest(parts=[TextPartInput(text=text)])
        response = await self._client.post(
            f"/session/{session_id}/message",
            json=request.model_dump(exclude_none=True),
            timeout=self._runtime.opencode_request_timeout_seconds,
        )
        response.raise_for_status()
        return Message.model_validate(response.json())

    async def run_command(self, session_id: str, command: str, arguments: str = "") -> Message:
        request = CommandRequest(command=command, arguments=arguments)
        response = await self._client.post(
            f"/session/{session_id}/command",
            json=request.model_dump(exclude_none=True),
            timeout=self._runtime.opencode_request_timeout_seconds,
        )
        response.raise_for_status()
        return Message.model_validate(response.json())

    async def abort_session(self, session_id: str) -> None:
        response = await self._client.post(f"/session/{session_id}/abort")
        response.raise_for_status()

    async def list_pending_permissions(self) -> list[PermissionRequest]:
        response = await self._client.get("/permission")
        response.raise_for_status()
        return [PermissionRequest.model_validate(item) for item in response.json()]

    async def reply_permission(
        self, request_id: str, reply: str, message: str | None = None
    ) -> bool:
        body = PermissionReplyRequest(reply=reply, message=message)
        raw = await self._client.post(
            f"/permission/{request_id}/reply",
            json=body.model_dump(exclude_none=True),
        )
        raw.raise_for_status()
        result = raw.json()
        if isinstance(result, bool):
            return result
        return True

    def _get_cache(self, key: str) -> Any | None:
        if self._cache_ttl_seconds is None:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at = entry.get("expires_at", 0.0)
        if self._clock() >= expires_at:
            self._cache.pop(key, None)
            return None
        return entry.get("value")

    def _set_cache(self, key: str, value: Any) -> None:
        if self._cache_ttl_seconds is not None:
            self._cache[key] = {
                "value": value,
                "expires_at": self._clock() + self._cache_ttl_seconds,
            }
