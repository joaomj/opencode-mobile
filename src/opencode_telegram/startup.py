import asyncio
import contextlib
import logging

from telegram import BotCommand, MenuButtonCommands
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from opencode_telegram.bridge_db import BridgeDB
from opencode_telegram.client import OpencodeClient
from opencode_telegram.config import RuntimeConfig, load_settings
from opencode_telegram.handlers import (
    handle_callback,
    handle_slash_command,
    handle_start,
    handle_text,
)
from opencode_telegram.logging_config import configure_logging
from opencode_telegram.models import Command as OpencodeCommand
from opencode_telegram.native_commands import HAMBUGER_DESCRIPTIONS
from opencode_telegram.poller import create_permission_poller
from opencode_telegram.session_state import SessionState

LOGGER = logging.getLogger(__name__)
TELEGRAM_COMMAND_DESCRIPTION_LIMIT = 256


def _truncate_desc(text: str, limit: int = TELEGRAM_COMMAND_DESCRIPTION_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_telegram_commands(commands: list[OpencodeCommand]) -> list[BotCommand]:
    bot_cmds: list[BotCommand] = []
    seen_names: set[str] = set()

    for name, desc in HAMBUGER_DESCRIPTIONS.items():
        seen_names.add(name)
        bot_cmds.append(BotCommand(command=name, description=desc))

    for cmd in commands:
        if cmd.name in seen_names:
            continue
        if cmd.source == "skill":
            continue
        desc = _truncate_desc(cmd.description or cmd.name)
        bot_cmds.append(BotCommand(command=cmd.name, description=desc))

    return bot_cmds


async def load_opencode_commands_resilient(
    client: OpencodeClient,
    runtime: RuntimeConfig,
) -> list[OpencodeCommand]:
    last_error: Exception | None = None
    attempts = max(runtime.opencode_startup_retries, 1)
    for attempt in range(attempts):
        try:
            return await client.list_commands()
        except Exception as exc:
            last_error = exc
            LOGGER.warning("list_commands attempt=%s failed: %s", attempt + 1, exc)
            if attempt + 1 < attempts:
                await asyncio.sleep(runtime.opencode_startup_retry_delay_seconds)
    LOGGER.error(
        "opencode server unreachable at startup after %s attempts; "
        "starting in degraded mode (no menu). last error: %s",
        attempts,
        last_error,
    )
    return []


async def run_bot() -> None:
    settings = load_settings()
    runtime = RuntimeConfig()
    configure_logging(runtime, settings.telegram_bot_token)
    LOGGER.info("starting opencode telegram bot base_url=%s", settings.opencode_base_url)
    client = OpencodeClient(settings=settings, runtime=runtime)
    bridge_db = BridgeDB(runtime.bridge_db_path)
    state = SessionState(bridge_db=bridge_db)
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data["settings"] = settings
    application.bot_data["client"] = client
    application.bot_data["state"] = state
    application.bot_data["runtime"] = runtime

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.COMMAND, handle_slash_command))

    commands = await load_opencode_commands_resilient(client=client, runtime=runtime)
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

        poller_task = create_permission_poller(
            client=client,
            state=state,
            application=application,
        )

        await asyncio.Event().wait()
    finally:
        if "poller_task" in locals() and poller_task is not None:
            poller_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poller_task
        LOGGER.info("stopping opencode telegram bot")
        if application.updater is not None and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        await application.shutdown()
        await client.close()
        bridge_db.close()
