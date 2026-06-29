import logging
import uuid

from telegram import CallbackQuery, Message, Update
from telegram.ext import ContextTypes

from opencode_telegram._logging_context import _CORRELATION_ID, session_context
from opencode_telegram.buttons import (
    CONTROL_NEW_SESSION,
    CONTROL_SESSIONS,
    CONTROL_STOP,
    control_panel_keyboard,
    sessions_keyboard,
)
from opencode_telegram.client import OpencodeClient
from opencode_telegram.commands import resolve_slash_command
from opencode_telegram.config import Settings
from opencode_telegram.format import truncate_telegram
from opencode_telegram.native_commands import (
    COMPACT_COMMANDS,
    EXIT_COMMANDS,
    NEW_SESSION_COMMANDS,
    SESSION_LIST_COMMANDS,
    UNSUPPORTED_TUI_COMMANDS,
    parse_native_command,
)
from opencode_telegram.permission_handler import parse_permission_callback
from opencode_telegram.session_state import SessionState

LOGGER = logging.getLogger(__name__)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_update(update, context):
        return
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(
        "opencode control panel",
        reply_markup=control_panel_keyboard(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_update(update, context):
        return
    if (
        update.effective_chat is None
        or update.effective_message is None
        or update.effective_message.text is None
    ):
        return

    client = _client(context)
    state = _state(context)
    chat_id = update.effective_chat.id
    text = update.effective_message.text
    session_id = await _ensure_session(client=client, state=state, chat_id=chat_id)

    with session_context(session_id):
        LOGGER.info("sending message chat_id=%s session_id=%s", chat_id, session_id)
        progress = await update.effective_message.reply_text("working...")
        try:
            message = await client.send_message(session_id=session_id, text=text)
            response_text = message.assistant_text() or "done"
            await progress.edit_text(response_text)
        except Exception:
            LOGGER.exception("send_message failed chat_id=%s", chat_id)
            await progress.edit_text("error: request failed")


async def handle_slash_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_update(update, context):
        return
    if (
        update.effective_chat is None
        or update.effective_message is None
        or update.effective_message.text is None
    ):
        return

    client = _client(context)
    state = _state(context)
    text = update.effective_message.text
    chat_id = update.effective_chat.id

    correlation_token = _CORRELATION_ID.set(uuid.uuid4().hex[:12])
    try:
        native_command = parse_native_command(text)
        if native_command is not None:
            await _handle_native_command(
                command=native_command,
                update=update,
                client=client,
                state=state,
            )
            return

        commands = await client.list_commands()
        parsed = resolve_slash_command(text, commands)
        if parsed is None:
            await update.effective_message.reply_text("unknown command")
            return

        session_id = await _ensure_session(
            client=client,
            state=state,
            chat_id=chat_id,
        )

        with session_context(session_id):
            LOGGER.info(
                "running command chat_id=%s session_id=%s command=%s",
                chat_id,
                session_id,
                parsed.name,
            )
            progress = await update.effective_message.reply_text("working...")
            try:
                message = await client.run_command(
                    session_id=session_id,
                    command=parsed.name,
                    arguments=parsed.arguments,
                )
                response_text = message.assistant_text() or "done"
                await progress.edit_text(response_text)
            except Exception:
                LOGGER.exception("run_command failed chat_id=%s", chat_id)
                await progress.edit_text("error: request failed")
    finally:
        _CORRELATION_ID.reset(correlation_token)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_update(update, context) or update.callback_query is None:
        return

    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        LOGGER.warning("answerCallbackQuery failed", exc_info=True)

    client = _client(context)
    state = _state(context)
    chat_id = query.message.chat_id if isinstance(query.message, Message) else None
    if chat_id is None or query.data is None:
        return

    data = query.data
    try:
        if data == CONTROL_NEW_SESSION:
            session = await client.create_session()
            await state.set_active_async(chat_id=chat_id, session_id=session.id)
            await query.edit_message_text(f"active session: {session.id}")
        elif data == CONTROL_SESSIONS:
            sessions = await client.list_sessions()
            await query.edit_message_text("sessions", reply_markup=sessions_keyboard(sessions))
        elif data == CONTROL_STOP:
            await _handle_stop(chat_id, client, state, query)
        elif data.startswith("ses:"):
            await _handle_select_session(data, chat_id, state, query)
        elif any(data.startswith(p) for p in ("pa:", "pd:", "par:", "pdr:")):
            await _handle_permission_callback(data=data, client=client, state=state, query=query)
    except Exception:
        LOGGER.exception("callback handler failed data=%s", data)


async def _handle_stop(
    chat_id: int,
    client: OpencodeClient,
    state: SessionState,
    query: CallbackQuery,
) -> None:
    session_id = await state.get_active_async(chat_id)
    if session_id is None:
        await query.edit_message_text("no active session")
    else:
        await client.abort_session(session_id)
        await query.edit_message_text("stopped")


async def _handle_select_session(
    data: str,
    chat_id: int,
    state: SessionState,
    query: CallbackQuery,
) -> None:
    session_id = data.removeprefix("ses:")
    await state.set_active_async(chat_id=chat_id, session_id=session_id)
    await query.edit_message_text(f"active session: {session_id}")


async def _handle_permission_callback(
    data: str,
    client: OpencodeClient,
    state: SessionState,
    query: CallbackQuery,
) -> None:
    parsed = parse_permission_callback(data)
    if parsed is None:
        await query.edit_message_text("invalid permission callback")
        return
    registration = await state.get_permission_async(parsed.short_id)
    if registration is None:
        await query.edit_message_text("permission request expired")
        return
    server_reply = "once" if not parsed.remember else "always"
    if parsed.response == "deny":
        server_reply = "reject"
    try:
        await client.reply_permission(
            request_id=registration.request_id,
            reply=server_reply,
        )
    except Exception:
        LOGGER.exception("failed to respond to permission")
        await query.edit_message_text("error: failed to respond to permission")
        return
    await state.remove_permission_async(registration.request_id)
    label = {"once": "allowed", "always": "allowed (always)", "reject": "denied"}.get(
        server_reply, server_reply
    )
    await query.edit_message_text(f"permission {label}")


async def _handle_native_command(
    command: str,
    update: Update,
    client: OpencodeClient,
    state: SessionState,
) -> None:
    if update.effective_chat is None or update.effective_message is None:
        return
    chat_id = update.effective_chat.id
    LOGGER.info("native command chat_id=%s command=%s", chat_id, command)

    if command == "help":
        await update.effective_message.reply_text(
            "Commands: /new, /sessions, /compact, /init, /share, /undo, /redo, /unshare. "
            "Custom opencode commands are also available via /command."
        )
    elif command in NEW_SESSION_COMMANDS:
        session = await client.create_session()
        await state.set_active_async(chat_id=chat_id, session_id=session.id)
        await update.effective_message.reply_text(f"active session: {session.id}")
    elif command in SESSION_LIST_COMMANDS:
        sessions = await client.list_sessions()
        await update.effective_message.reply_text(
            "sessions",
            reply_markup=sessions_keyboard(sessions),
        )
    elif command in COMPACT_COMMANDS | {"init", "share", "undo", "redo", "unshare"}:
        await _run_native_session_command(command, chat_id, update, client, state)
    elif command in EXIT_COMMANDS:
        await update.effective_message.reply_text("/exit only applies to the local TUI.")
    elif command in UNSUPPORTED_TUI_COMMANDS:
        await update.effective_message.reply_text(
            f"/{command} is a local TUI display action and is not available in Telegram."
        )


async def _run_native_session_command(
    command: str,
    chat_id: int,
    update: Update,
    client: OpencodeClient,
    state: SessionState,
) -> None:
    if update.effective_message is None:
        return
    session_id = await _ensure_session(client=client, state=state, chat_id=chat_id)
    with session_context(session_id):
        message = await client.run_command(
            session_id=session_id,
            command=command,
            arguments="",
        )
        await update.effective_message.reply_text(
            truncate_telegram(message.assistant_text() or "done")
        )


def _client(context: ContextTypes.DEFAULT_TYPE) -> OpencodeClient:
    client = context.application.bot_data["client"]
    if not isinstance(client, OpencodeClient):
        raise TypeError("bot client is not configured")
    return client


def _state(context: ContextTypes.DEFAULT_TYPE) -> SessionState:
    state = context.application.bot_data["state"]
    if not isinstance(state, SessionState):
        raise TypeError("session state is not configured")
    return state


async def _ensure_session(client: OpencodeClient, state: SessionState, chat_id: int) -> str:
    session_id = await state.get_active_async(chat_id)
    if session_id is not None:
        await state.set_active_async(chat_id=chat_id, session_id=session_id)
        return session_id
    session = await client.create_session()
    await state.set_active_async(chat_id=chat_id, session_id=session.id)
    return session.id


def _is_allowed_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.application.bot_data["settings"]
    if not isinstance(settings, Settings):
        return False
    user_id = update.effective_user.id if update.effective_user is not None else None
    return user_id == settings.telegram_allowed_user_id
