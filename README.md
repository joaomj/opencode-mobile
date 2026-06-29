# opencode-telegram

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Telegram bridge for [opencode](https://opencode.ai) — control your local AI coding
assistant from your phone.**

Send prompts, run commands, approve file operations, and manage sessions — all
via Telegram. The bridge is a thin transport layer: all execution happens on the
opencode server. No VPN, no public IP, no webhooks needed.

## Features

- **Instant messaging to AI coding** — type a message, get a response
- **Slash commands** — `/commit`, `/new`, `/sessions`, and any server-registered command
- **Permission approvals** — Allow/Deny inline buttons for file operations (git add, commit, etc.)
- **Multi-session** — start, switch, or end sessions from your phone
- **Single binary dependency** — Python 3.11+, `uv`, and a running opencode server
- **No public endpoints** — bot connects outbound to Telegram (polling, not webhooks)
- **Single-user security** — only your Telegram user ID is authorised

## Quick Start

### Prerequisites

- **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)** (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A running **[opencode](https://opencode.ai/docs/server/)** server on your machine
- A **Telegram bot token** from [@BotFather](https://t.me/BotFather)
- Your **Telegram user ID** from [@userinfobot](https://t.me/userinfobot)

### Install

```bash
git clone <repo-url>
cd opencode-mobile
uv sync
```

### Configure

```bash
cp .env.example .env
```

Edit `.env` with your bot token, user ID, and opencode credentials:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-ABCdefGHI
TELEGRAM_ALLOWED_USER_ID=123456789
OPENCODE_BASE_URL=http://127.0.0.1:4096
OPENCODE_SERVER_USERNAME=opencode
OPENCODE_SERVER_PASSWORD=your-password
```

### Run

Terminal 1 — start the opencode server:

```bash
opencode serve --print-logs
```

Terminal 2 — start the bridge:

```bash
uv run opencode-telegram
```

Open Telegram, find your bot, and send `/start`. You're in.

## Usage

### Text prompts

Any plain text message is forwarded as a prompt to the current session. The bot
replies with the assistant's full response.

### Slash commands

| Command | Action |
|---------|--------|
| `/start` | Show control panel |
| `/new` | Create a new session |
| `/sessions` | List and switch sessions |
| `/resume` or `/continue` | Resume previous session |
| `/compact` or `/summarize` | Compact session history |
| `/init` | Run AGENTS.md setup |
| `/share` / `/unshare` | Share or unshare session |
| `/undo` / `/redo` | Undo or redo last message |
| `/exit` / `/quit` / `/q` | End current session |
| `/help` | Show available commands |
| _any server command_ | Auto-discovered at startup |

Custom commands registered on the opencode server (via tools, plugins, etc.) are
automatically loaded at startup and available as Telegram slash commands.

### Permission approvals

When the AI needs to run a sensitive operation (e.g., `git add`, `git commit`),
the bot shows an inline keyboard:

```
Permission request: bash
git add src/opencode_telegram/...

[ Allow ] [ Deny ]
[ Allow + remember ] [ Deny + remember ]
```

Tap **Allow** to approve once, or **Allow + remember** to save the rule for
future operations in the same session.

### Multi-session

- `/new` — start fresh (previous sessions remain accessible)
- `/sessions` — pick a different session
- `/exit` — end the current session

## Configuration

All settings are environment variables in `.env`. See `.env.example` for defaults.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Telegram bot token |
| `TELEGRAM_ALLOWED_USER_ID` | Yes | — | Your Telegram user ID |
| `OPENCODE_BASE_URL` | Yes | `http://127.0.0.1:4096` | opencode server URL |
| `OPENCODE_SERVER_USERNAME` | Yes | `opencode` | API username |
| `OPENCODE_SERVER_PASSWORD` | Yes | — | API password |
| `OPENCODE_REQUEST_TIMEOUT_SECONDS` | No | `200.0` | Global HTTP timeout |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `LOG_FILE` | No | `logs/opencode-telegram.log` | Log file path |
| `TELEGRAM_HTTP_LOGS` | No | `false` | Enable HTTP request logging |
| `BRIDGE_DB_PATH` | No | `~/.local/state/…/bridge.db` | SQLite path for session mapping |
| `OPENCODE_STARTUP_RETRIES` | No | `5` | Retries on server connect |
| `OPENCODE_STARTUP_RETRY_DELAY_SECONDS` | No | `2.0` | Delay between retries |

## Architecture

The bridge runs two concurrent asyncio tasks:

- **Main handler** — receives Telegram input, calls sync REST endpoint, blocks
  until full response, delivers final answer.
- **Permission poller** — every 2s calls `GET /permission`, checks for pending
  requests, shows Telegram Allow/Deny buttons.

Data flow:

```
Telegram ───► handle_text() / handle_slash_command()
                │
                ├─ POST /session/{id}/message|command  (blocks)
                │   └─ edit "working…" with final response
                │
Background task: GET /permission (every 2s)
                  └─ send Allow/Deny buttons for pending requests
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the detailed engineering
reference.

## Development

```bash
# Run tests
uv run pytest -v

# Type check
uv run mypy

# Lint
uv run ruff check .

# All checks
uv run pytest -v && uv run mypy && uv run ruff check .
```

## License

MIT — see [LICENSE](LICENSE).

Copyright (c) 2025-2026 Joao Marcos Visotaky Junior
