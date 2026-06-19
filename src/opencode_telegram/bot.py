import asyncio
import contextlib
import json
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram import BotCommand, CallbackQuery, MenuButtonCommands, Message, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from opencode_telegram.buttons import (
    CONTROL_NEW_SESSION,
    CONTROL_SESSIONS,
    CONTROL_STOP,
    ITEMS_PER_PAGE,
    control_panel_keyboard,
    paginated_agent_keyboard,
    paginated_model_keyboard,
    provider_list_keyboard,
    sessions_keyboard,
)
from opencode_telegram.commands import resolve_slash_command
from opencode_telegram.config import RuntimeConfig, Settings, load_settings
from opencode_telegram.format import split_long_message, truncate_telegram
from opencode_telegram.native_commands import (
    COMPACT_COMMANDS,
    EXIT_COMMANDS,
    HAMBUGER_DESCRIPTIONS,
    NEW_SESSION_COMMANDS,
    SESSION_LIST_COMMANDS,
    UNSUPPORTED_TUI_COMMANDS,
    parse_native_command,
)
from opencode_telegram.opencode_client import Command as OpencodeCommand
from opencode_telegram.opencode_client import OpencodeClient
from opencode_telegram.session_state import SessionState

TELEGRAM_COMMAND_DESCRIPTION_LIMIT = 256
TELEGRAM_COMMAND_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,32}$")
LOGGER = logging.getLogger(__name__)


def is_allowed_user(user_id: int | None, settings: Settings) -> bool:
    return user_id == settings.telegram_allowed_user_id


def build_telegram_commands(commands: list[OpencodeCommand]) -> list[BotCommand]:
    bot_cmds: list[BotCommand] = []
    seen_names: set[str] = set()

    for name, desc in HAMBUGER_DESCRIPTIONS.items():
        if not TELEGRAM_COMMAND_NAME_PATTERN.fullmatch(name):
            continue
        seen_names.add(name)
        bot_cmds.append(BotCommand(command=name, description=_truncate_desc(desc)))

    for cmd in commands:
        if cmd.name in seen_names:
            continue
        if not TELEGRAM_COMMAND_NAME_PATTERN.fullmatch(cmd.name):
            continue
        desc = _truncate_desc(cmd.description or cmd.name)
        bot_cmds.append(BotCommand(command=cmd.name, description=desc))

    return bot_cmds


def _truncate_desc(text: str, limit: int = TELEGRAM_COMMAND_DESCRIPTION_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


async def run_bot() -> None:
    settings = load_settings()
    runtime = RuntimeConfig()
    _configure_logging(runtime)
    LOGGER.info("starting opencode telegram bot base_url=%s", settings.opencode_base_url)
    client = OpencodeClient(settings=settings, runtime=runtime)
    state = SessionState()
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["client"] = client
    application.bot_data["state"] = state
    application.bot_data["runtime"] = runtime

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.COMMAND, handle_slash_command))

    commands = await client.list_commands()
    LOGGER.info("loaded opencode commands count=%s", len(commands))
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    await application.bot.set_my_commands(build_telegram_commands(commands))

    try:
        await application.initialize()
        await application.start()
        if application.updater is None:
            raise RuntimeError("telegram updater is not configured")
        await application.updater.start_polling()
        LOGGER.info("telegram polling started")
        event_task = _create_event_log_task(client=client, runtime=runtime)
        await asyncio.Event().wait()
    finally:
        if "event_task" in locals() and event_task is not None:
            event_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await event_task
        LOGGER.info("stopping opencode telegram bot")
        if application.updater is not None and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        await application.shutdown()
        await client.close()


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
    runtime = _runtime(context)
    chat_id = update.effective_chat.id
    session_id = await _ensure_session(client=client, state=state, chat_id=chat_id)
    agent = await state.get_agent_async(chat_id)
    model = await state.get_model_async(chat_id)
    LOGGER.info("forwarding prompt async chat_id=%s session_id=%s", chat_id, session_id)

    await client.send_prompt_async(
        session_id=session_id,
        text=update.effective_message.text,
        agent=agent,
        model=model,
    )

    progress = await update.effective_message.reply_text("working...")
    result = await _poll_for_result(
        client=client,
        session_id=session_id,
        runtime=runtime,
    )
    if result is not None:
        for chunk in split_long_message(result, runtime=runtime):
            await progress.reply_text(chunk)
        await progress.delete()
    else:
        await progress.edit_text("error: no response from opencode")


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
    native_command = parse_native_command(update.effective_message.text)
    if native_command is not None:
        await _handle_native_command(
            command=native_command,
            update=update,
            client=client,
            state=state,
        )
        return

    commands = await client.list_commands()
    parsed = resolve_slash_command(update.effective_message.text, commands)
    if parsed is None:
        await update.effective_message.reply_text("unknown command")
        return

    chat_id = update.effective_chat.id
    session_id = await _ensure_session(client=client, state=state, chat_id=chat_id)
    agent = await state.get_agent_async(chat_id)
    model = await state.get_model_async(chat_id)
    LOGGER.info(
        "forwarding opencode command chat_id=%s session_id=%s command=%s",
        chat_id,
        session_id,
        parsed.name,
    )
    message = await client.run_command(
        session_id=session_id,
        command=parsed.name,
        arguments=parsed.arguments,
        agent=agent,
        model=model,
    )
    await update.effective_message.reply_text(truncate_telegram(message.assistant_text() or "done"))


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed_update(update, context) or update.callback_query is None:
        return

    query = update.callback_query
    await query.answer()
    client = _client(context)
    state = _state(context)
    chat_id = query.message.chat_id if isinstance(query.message, Message) else None
    if chat_id is None or query.data is None:
        return
    await _handle_callback_data(
        data=query.data,
        chat_id=chat_id,
        client=client,
        state=state,
        query=query,
    )


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


async def _handle_select_agent(
    data: str,
    chat_id: int,
    state: SessionState,
    query: CallbackQuery,
) -> None:
    agent_name = data.removeprefix("sa:")
    await state.set_agent_async(chat_id=chat_id, agent=agent_name)
    await query.edit_message_text(f"active agent: {agent_name}")
    LOGGER.info("selected agent chat_id=%s agent=%s", chat_id, agent_name)


async def _handle_select_model(
    data: str,
    chat_id: int,
    state: SessionState,
    query: CallbackQuery,
) -> None:
    option_id = data.removeprefix("sm:")
    model = await state.get_model_option_async(option_id)
    if model is None:
        await query.edit_message_text("invalid model selection")
    else:
        await state.set_model_async(
            chat_id=chat_id,
            provider_id=model.provider_id,
            model_id=model.model_id,
        )
        await query.edit_message_text(f"active model: {model.provider_id}/{model.model_id}")
        LOGGER.info(
            "selected model chat_id=%s model=%s/%s",
            chat_id,
            model.provider_id,
            model.model_id,
        )


async def _handle_callback_data(
    data: str,
    chat_id: int,
    client: OpencodeClient,
    state: SessionState,
    query: CallbackQuery,
) -> None:
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
    elif data.startswith("sa:"):
        await _handle_select_agent(data, chat_id, state, query)
    elif data.startswith("sm:"):
        await _handle_select_model(data, chat_id, state, query)
    elif data == "pg:cancel":
        await query.delete_message()
    elif data.startswith("sp:"):
        provider_id = data.removeprefix("sp:")
        await _show_models_page(
            query=query,
            client=client,
            state=state,
            provider_id=provider_id,
            page=0,
        )
    elif data.startswith("pg:") or data.startswith("ag:"):
        await _handle_page_nav(data, query, client, state)
    elif data.startswith("ap:"):
        await _handle_agent_page(data, query, client)


async def _handle_page_nav(
    data: str,
    query: CallbackQuery,
    client: OpencodeClient,
    state: SessionState,
) -> None:
    prefix = data[:2]
    try:
        page = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    if prefix == "pg":
        msg = query.message
        text = msg.text if isinstance(msg, Message) and msg.text else ""
        provider_id = _extract_provider_id(text)
        if provider_id:
            await _show_models_page(
                query=query,
                client=client,
                state=state,
                provider_id=provider_id,
                page=page,
            )
    elif prefix == "ag":
        await _show_agents_page(query=query, client=client, page=page)


async def _handle_agent_page(data: str, query: CallbackQuery, client: OpencodeClient) -> None:
    try:
        page = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        return
    await _show_agents_page(query=query, client=client, page=page)


def _extract_provider_id(text: str) -> str | None:
    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if stripped.startswith("provider:"):
            return stripped.removeprefix("provider:").strip()
    return None


async def _show_models_page(
    query: CallbackQuery,
    client: OpencodeClient,
    state: SessionState,
    provider_id: str,
    page: int,
) -> None:
    providers = await client.list_config_providers()
    provider = next((p for p in providers.providers if p.id == provider_id), None)
    if provider is None:
        await query.edit_message_text("provider not found")
        return

    items: list[tuple[str, str]] = []
    for model_id, model in provider.models.items():
        label = f"{provider.name or provider.id}: {model.name or model_id}"
        option_id = await state.register_model_option_async(
            provider_id=provider.id,
            model_id=model_id,
        )
        items.append((option_id, label))

    total_pages = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    actual_page = min(page, total_pages - 1)
    header = f"provider: {provider_id}"
    keyboard = paginated_model_keyboard(items, actual_page, total_pages)
    await query.edit_message_text(header, reply_markup=keyboard)


async def _show_agents_page(
    query: CallbackQuery,
    client: OpencodeClient,
    page: int,
) -> None:
    agents = [agent for agent in await client.list_agents() if agent.mode != "subagent"]
    agent_names = [agent.name for agent in agents]
    total_pages = max(1, (len(agent_names) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    actual_page = min(page, total_pages - 1)
    keyboard = paginated_agent_keyboard(agent_names, actual_page, total_pages)
    await query.edit_message_text("select agent", reply_markup=keyboard)


async def _poll_for_result(
    client: OpencodeClient,
    session_id: str,
    runtime: RuntimeConfig,
) -> str | None:
    deadline = asyncio.get_event_loop().time() + runtime.opencode_request_timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(runtime.prompt_poll_interval_seconds)
        entry = await client.get_last_message(session_id)
        if entry is not None:
            text = entry.assistant_text()
            if text:
                return text
    return None


def _is_allowed_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.application.bot_data["settings"]
    if not isinstance(settings, Settings):
        return False
    user_id = update.effective_user.id if update.effective_user is not None else None
    return is_allowed_user(user_id=user_id, settings=settings)


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


def _runtime(context: ContextTypes.DEFAULT_TYPE) -> RuntimeConfig:
    runtime = context.application.bot_data.get("runtime")
    if not isinstance(runtime, RuntimeConfig):
        return RuntimeConfig()
    return runtime


async def _ensure_session(client: OpencodeClient, state: SessionState, chat_id: int) -> str:
    session_id = await state.get_active_async(chat_id)
    if session_id is not None:
        return session_id
    session = await client.create_session()
    await state.set_active_async(chat_id=chat_id, session_id=session.id)
    return session.id


async def _handle_native_command(
    command: str,
    update: Update,
    client: OpencodeClient,
    state: SessionState,
) -> None:
    if update.effective_chat is None or update.effective_message is None:
        return
    chat_id = update.effective_chat.id
    LOGGER.info("handling native command chat_id=%s command=%s", chat_id, command)

    if command == "agents":
        await _reply_agents(update=update, client=client)
    elif command == "models":
        await _reply_models(update=update, client=client, state=state)
    elif command == "help":
        await update.effective_message.reply_text(
            "Native commands: /agents, /models, /new, /sessions, /stop via button, "
            "/compact, /init, /share, /undo, /redo, /unshare. "
            "Custom opencode commands are forwarded when exposed by /command."
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


async def _reply_agents(update: Update, client: OpencodeClient) -> None:
    if update.effective_message is None:
        return
    agents = [agent for agent in await client.list_agents() if agent.mode != "subagent"]
    agent_names = [agent.name for agent in agents]
    total_pages = max(1, (len(agent_names) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    keyboard = paginated_agent_keyboard(agent_names, 0, total_pages)
    await update.effective_message.reply_text("select agent", reply_markup=keyboard)


async def _reply_models(update: Update, client: OpencodeClient, state: SessionState) -> None:
    if update.effective_message is None:
        return
    providers = await client.list_config_providers()
    if len(providers.providers) == 1:
        provider = providers.providers[0]
        await _show_models_for_provider(
            update=update,
            client=client,
            state=state,
            provider_id=provider.id,
        )
    else:
        provider_list = [
            (p.id, p.name or p.id)
            for p in providers.providers
        ]
        await update.effective_message.reply_text(
            "select provider",
            reply_markup=provider_list_keyboard(provider_list),
        )


async def _show_models_for_provider(
    update: Update,
    client: OpencodeClient,
    state: SessionState,
    provider_id: str,
) -> None:
    if update.effective_message is None:
        return
    providers = await client.list_config_providers()
    provider = next((p for p in providers.providers if p.id == provider_id), None)
    if provider is None:
        await update.effective_message.reply_text("provider not found")
        return

    items: list[tuple[str, str]] = []
    for model_id, model in provider.models.items():
        label = f"{model.name or model_id}"
        option_id = await state.register_model_option_async(
            provider_id=provider.id,
            model_id=model_id,
        )
        items.append((option_id, label))

    total_pages = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    keyboard = paginated_model_keyboard(items, 0, total_pages)
    header = f"provider: {provider_id}"
    await update.effective_message.reply_text(header, reply_markup=keyboard)


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
    agent = await state.get_agent_async(chat_id)
    model = await state.get_model_async(chat_id)
    message = await client.run_command(
        session_id=session_id,
        command=command,
        arguments="",
        agent=agent,
        model=model,
    )
    await update.effective_message.reply_text(truncate_telegram(message.assistant_text() or "done"))


def _configure_logging(runtime: RuntimeConfig) -> None:
    log_path = Path(runtime.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, runtime.log_level))

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=runtime.log_max_bytes,
        backupCount=runtime.log_backup_count,
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    if runtime.telegram_http_logs:
        logging.getLogger("httpx").setLevel(logging.DEBUG)
    else:
        logging.getLogger("httpx").setLevel(logging.WARNING)

    LOGGER.info("logging to file: %s", log_path)


def _create_event_log_task(
    client: OpencodeClient,
    runtime: RuntimeConfig,
) -> asyncio.Task[None] | None:
    if not runtime.opencode_event_logs:
        return None
    return asyncio.create_task(_log_opencode_events(client))


async def _log_opencode_events(client: OpencodeClient) -> None:
    LOGGER.info("opencode SSE event logging started")
    async for line in client.events():
        event_name = _safe_sse_event_name(line)
        if event_name is not None:
            LOGGER.info("opencode event type=%s", event_name)


def _safe_sse_event_name(line: str) -> str | None:
    if line.startswith("event:"):
        return line.removeprefix("event:").strip()
    if not line.startswith("data:"):
        return None
    data = line.removeprefix("data:").strip()
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        payload_type = payload.get("type")
        if isinstance(payload_type, str):
            return payload_type
        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            nested_type = nested_payload.get("type")
            if isinstance(nested_type, str):
                return nested_type
    return None
