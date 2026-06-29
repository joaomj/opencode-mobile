#!/usr/bin/env python3
"""End-to-end test: starts opencode server, exercises the bot flow, shows result.

Usage:
  1. Make sure .env exists with TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USER_ID
  2. uv run python3 scripts/e2e_test.py

The script:
  - Starts `opencode serve` in the background
  - Exercises the bot's prompt flow using the real opencode API (no Telegram needed)
  - Shows streaming response and final answer
  - Shuts everything down cleanly
"""

import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(name)-30s %(levelname)-8s %(message)s",
    stream=sys.stdout,
)
# Silence noisy libs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

LOG = logging.getLogger("e2e")

PROMPT = "Write a one-sentence haiku about asynchronous programming."


class ServerProc:
    """Manages the opencode server subprocess."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

    def start(self) -> None:
        LOG.info("Starting opencode server...")
        self._proc = subprocess.Popen(
            ["opencode", "serve", "--print-logs", "--log-level", "WARN"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def wait_for_ready(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            assert self._proc and self._proc.stdout
            line = self._proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.rstrip()
            LOG.debug("  server: %s", line)
            if "listening on" in line.lower() or "http" in line.lower():
                LOG.info("  server ready: %s", line)
                return
        raise TimeoutError("opencode server did not start in time")

    def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            LOG.info("Server stopped")


async def run_prompt_flow(client, session_id: str) -> str:
    """Send a prompt, consume SSE events, return the final assistant answer."""

    from opencode_telegram.opencode_client import (
        EventMessagePartUpdated,
        EventMessageUpdated,
        EventSessionIdle,
    )

    LOG.info("")
    LOG.info("─" * 50)
    LOG.info("Sending prompt: %s", PROMPT)
    LOG.info("─" * 50)

    await client.send_prompt_async(
        session_id=session_id,
        text=PROMPT,
    )

    accumulated = ""
    message_id = None

    async for line in client.events():
        from opencode_telegram.opencode_client import parse_event_line_with_id

        _event_id, event = parse_event_line_with_id(line)
        if event is None:
            continue

        if isinstance(event, EventMessagePartUpdated):
            part = event.properties.part
            if part.type == "text" and part.text:
                text = part.text
                if text != accumulated:
                    delta = text[len(accumulated):] if text.startswith(accumulated) else text
                    print(delta, end="", flush=True)
                    accumulated = text

        elif isinstance(event, EventMessageUpdated):
            info = event.properties.info
            if info.id:
                message_id = info.id
            if info.role == "assistant" and info.time and info.time.completed:
                print()

        elif isinstance(event, EventSessionIdle):
            LOG.info("")
            LOG.info("─" * 50)
            LOG.info("Session idle — prompt flow complete")
            break

    return accumulated


async def main() -> None:
    from opencode_telegram.config import RuntimeConfig, load_settings
    from opencode_telegram.opencode_client import OpencodeClient

    settings = load_settings()
    runtime = RuntimeConfig()

    # ── 1. Start opencode server ──────────────────────────────────────
    server = ServerProc()
    try:
        server.start()
        server.wait_for_ready(timeout=15.0)
    except (FileNotFoundError, TimeoutError) as exc:
        LOG.error("Failed to start server: %s", exc)
        LOG.error("Make sure `opencode` CLI is installed and available on PATH.")
        sys.exit(1)

    # ── 2. Connect to opencode API ────────────────────────────────────
    client = OpencodeClient(settings=settings, runtime=runtime)

    # Create a session
    session = await client.create_session()
    LOG.info("Created session: %s", session.id)

    # Show configured defaults
    cfg = await client.get_default_model_config()
    if cfg:
        LOG.info("Default agent: %s | model: %s/%s", cfg[0], cfg[1][0], cfg[1][1])

    # ── 3. Run prompt flow ────────────────────────────────────────────
    try:
        answer = await run_prompt_flow(client, session.id)
        LOG.info("")
        LOG.info("=" * 50)
        LOG.info("FINAL ANSWER (%d chars):", len(answer))
        LOG.info("=" * 50)
        print(answer)
        LOG.info("=" * 50)
        LOG.info("SUCCESS: End-to-end flow completed without errors.")
    except Exception:
        LOG.exception("Prompt flow failed")
        sys.exit(1)
    finally:
        await client.close()

    # ── 4. Cleanup ────────────────────────────────────────────────────
    server.stop()
    LOG.info("All done.")


if __name__ == "__main__":
    asyncio.run(main())
