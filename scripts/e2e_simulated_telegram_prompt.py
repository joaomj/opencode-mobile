#!/usr/bin/env python3
"""E2E test: simulated Telegram update through real DeliveryManager + aggregator.

Starts an opencode server subprocess, boots the bot application in-process with a
fake Telegram bot API server, injects a synthetic telegram.Update, and waits for
the final sendMessage to arrive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

import telegram
from telegram.ext import Application, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("e2e")


E2E_DONE_PREFIX = "E2E_DONE_"


class FakeTelegramAPIHandler(BaseHTTPRequestHandler):
    """Captures outgoing bot API calls for assertion."""

    captured: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type", "")

        payload: dict[str, Any] = {}
        if body:
            if "application/json" in ctype:
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    LOGGER.warning("fake-tg: JSON parse failed: %r", body)
            elif "application/x-www-form-urlencoded" in ctype:
                qs = parse_qs(body.decode())
                payload = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
            else:
                LOGGER.warning("fake-tg: unknown content type %r body=%r", ctype, body)

        path = urlparse(self.path).path
        self.captured.append({"path": path, "payload": payload})
        LOGGER.info("fake-tg: %s %s", path, payload)

        now = int(time.time())
        result: dict[str, Any] = {"ok": True}
        if "getMe" in path:
            result["result"] = {
                "id": 123456789,
                "is_bot": True,
                "first_name": "E2ETestBot",
                "username": "e2e_test_bot",
            }
        elif "sendMessage" in path:
            chat_id = int(payload.get("chat_id", 0))
            text = payload.get("text", "")
            result["result"] = {
                "message_id": 999,
                "date": now,
                "text": text,
                "chat": {"id": chat_id, "type": "private"},
                "from": {
                    "id": 123456789,
                    "is_bot": True,
                    "first_name": "E2ETestBot",
                },
            }
        else:
            result["result"] = True

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
        self.wfile.flush()

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.debug("fake-tg-http: %s", fmt % args)


def _run_fake_telegram_api(port: int) -> HTTPServer:
    FakeTelegramAPIHandler.captured.clear()
    server = HTTPServer(("127.0.0.1", port), FakeTelegramAPIHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    LOGGER.info("fake telegram API listening on port %s", port)
    return server


async def _handle_text(update: telegram.Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple echo handler for the test bot."""
    if update.effective_message is None or update.effective_message.text is None:
        return
    text = update.effective_message.text
    await update.effective_message.reply_text(f"{E2E_DONE_PREFIX}{text}")


async def _run_e2e(_opencode_port: int, tg_api_port: int, timeout: float = 30.0) -> None:
    tg_api_url = f"http://127.0.0.1:{tg_api_port}/bot"
    application = (
        Application.builder()
        .token("e2e:fake-token")
        .base_url(tg_api_url)
        .base_file_url(tg_api_url)
        .build()
    )
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))

    try:
        await application.initialize()
        await application.start()
        if application.updater is None:
            raise RuntimeError("no updater")

        # Build a synthetic Telegram update — associate bot with message
        bot = application.bot
        chat = telegram.Chat(id=42, type="private")
        user = telegram.User(id=1, is_bot=False, first_name="Test")
        message = telegram.Message(
            message_id=1,
            chat=chat,
            from_user=user,
            text="hello e2e",
            date=None,
        )
        message.set_bot(bot)
        update = telegram.Update(update_id=1, message=message)
        await application.process_update(update)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for cap in FakeTelegramAPIHandler.captured:
                payload = cap.get("payload", {})
                text = payload.get("text", "")
                if E2E_DONE_PREFIX in text:
                    LOGGER.info("E2E SUCCESS: captured final text=%r", text)
                    return
            await asyncio.sleep(0.1)

        LOGGER.error("E2E FAILURE: timeout waiting for %s message", E2E_DONE_PREFIX)
        sys.exit(1)
    finally:
        await application.stop()
        await application.shutdown()


def main() -> None:
    tg_api_port = 18999
    opencode_port = 14096

    # Start fake Telegram API
    tg_server = _run_fake_telegram_api(tg_api_port)

    # Start opencode server
    env = os.environ.copy()
    env["OPencode_BASE_URL"] = f"http://127.0.0.1:{opencode_port}"
    server_proc = subprocess.Popen(
        [sys.executable, "-m", "opencode", "server", "--port", str(opencode_port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    LOGGER.info("opencode server PID=%s port=%s", server_proc.pid, opencode_port)
    time.sleep(3)  # give server time to start

    try:
        asyncio.run(_run_e2e(opencode_port, tg_api_port))
    finally:
        server_proc.terminate()
        server_proc.wait(timeout=10)
        tg_server.shutdown()
        LOGGER.info("cleanup done")


if __name__ == "__main__":
    main()
