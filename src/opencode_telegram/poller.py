import asyncio
import logging
from typing import Any

from telegram.ext import Application

from opencode_telegram.client import OpencodeClient
from opencode_telegram.models import PermissionRequest
from opencode_telegram.permission_handler import build_permission_keyboard
from opencode_telegram.session_state import SessionState

LOGGER = logging.getLogger(__name__)
_DEFAULT_POLL_INTERVAL = 2.0


def _format_permission_text(req: PermissionRequest) -> str:
    lines = [f"*Permission request:* {req.permission}"]
    cmd = req.metadata.get("command")
    if cmd:
        lines.append(f"")
        lines.append(f"```\n{cmd}\n```")
    if req.patterns:
        lines.append(f"")
        lines.append(f"matches: `{req.patterns[0]}`")
        if len(req.patterns) > 1:
            for p in req.patterns[1:]:
                lines.append(f"         `{p}`")
    return "\n".join(lines)


def create_permission_poller(
    client: OpencodeClient,
    state: SessionState,
    application: Application[Any, Any, Any, Any, Any, Any],
) -> asyncio.Task[None]:
    return asyncio.create_task(
        _permission_poller(client, state, application)
    )


async def _permission_poller(
    client: OpencodeClient,
    state: SessionState,
    application: Application[Any, Any, Any, Any, Any, Any],
) -> None:
    interval = _DEFAULT_POLL_INTERVAL
    while True:
        await asyncio.sleep(interval)
        try:
            requests = await client.list_pending_permissions()
        except Exception:
            LOGGER.warning("permission poll failed", exc_info=True)
            continue

        if not requests:
            continue

        for req in requests:
            if state.has_tracked_permission(req.id):
                continue
            chat_id = await state.get_chat_for_session_async(req.session_id)
            if chat_id is None:
                LOGGER.warning(
                    "no chat mapping for session_id=%s permission_id=%s",
                    req.session_id,
                    req.id,
                )
                continue
            short_id = await state.register_permission_async(
                session_id=req.session_id,
                request_id=req.id,
            )
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text=_format_permission_text(req),
                    reply_markup=build_permission_keyboard(short_id=short_id),
                )
            except Exception:
                LOGGER.exception(
                    "failed to send permission message chat_id=%s", chat_id
                )
