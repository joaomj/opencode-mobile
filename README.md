# opencode-telegram

A **Telegram bot bridge** for controlling a local [opencode](https://github.com/anomalyco/opencode) instance from your phone.

Start AI coding sessions, send prompts, switch agents/models, and manage sessions — all via Telegram.

## How It Works

```
Your Phone (Telegram)  ──►  opencode-telegram (this bot)  ──►  opencode REST API (localhost)
                                   │
                           reads .env for:
                           - TELEGRAM_BOT_TOKEN
                           - OPENCODE_BASE_URL / credentials
```

The bot forwards your Telegram messages to opencode's HTTP API and streams responses back. Only you (the configured `TELEGRAM_ALLOWED_USER_ID`) can interact with it.

## Prerequisites

- **Python 3.11+** (this project requires `>=3.11`; tested with 3.11–3.13)
- **uv** (fast Python package manager) — install with:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- A running [opencode](https://github.com/anomalyco/opencode) server with its REST API enabled (see below).
- A **Telegram bot token** from [@BotFather](https://t.me/BotFather)
- Your **Telegram user ID** (use [@userinfobot](https://t.me/userinfobot) to find it)

### Running the opencode server with logs

See the [opencode server docs](https://opencode.ai/docs/server/) for full setup instructions.

From the repo root, start the server in a terminal with:

```bash
opencode serve --print-logs
```

By default, opencode writes logs only to files at `~/.local/share/opencode/log/`. To see logs in the terminal:

```bash
# Server mode with terminal logs
opencode serve --print-logs

# With verbose debug output
opencode serve --print-logs --log-level DEBUG

# CLI mode (non-server) with terminal logs
opencode --print-logs
```

You can also set a persistent log level in `~/.config/opencode/opencode.jsonc`:

```jsonc
{
  "logLevel": "DEBUG"
}
```

## Quick Start

### 1. Get a Telegram bot token

Open Telegram, message [@BotFather](https://t.me/BotFather), and run:

```
/newbot
```

Follow the prompts to name your bot. BotFather will give you a token like:

```
1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-ABCdefGHI
```

Save this — you'll need it in step 4.

### 2. Find your Telegram user ID

Message [@userinfobot](https://t.me/userinfobot) and send `/start`. It will reply with your numeric user ID:

```
Id: 123456789
```

Save this — you'll need it in step 4.

### 3. Clone and install dependencies

```bash
# Clone the repository
git clone <repo-url>
cd opencode-mobile

# Install uv if you don't have it (macOS/Linux):
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a virtual environment and install all dependencies
uv sync
```

### 4. Configure the bot

```bash
# Copy the example config file
cp .env.example .env
```

Open `.env` in any text editor. Fill in the values you saved from steps 1 and 2:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-ABCdefGHI
TELEGRAM_ALLOWED_USER_ID=123456789
```

Make sure the **opencode server is already running** on your machine. The default URL is `http://127.0.0.1:4096`. If your opencode instance uses a different port or a password, set those too:

```env
OPENCODE_BASE_URL=http://127.0.0.1:4096
OPENCODE_SERVER_USERNAME=opencode
OPENCODE_SERVER_PASSWORD=your-password-here
```

Save the file.

### 5. Start the services

Open two terminals in the repo root.

Terminal 1 starts the opencode server:

```bash
opencode serve --print-logs
```

Terminal 2 starts the Telegram bot:

```bash
uv run opencode-telegram
```

You should see log output like:

```
2025-01-01 12:00:00 INFO  opencode_telegram.bot Bot started — polling for updates...
```

If you see errors, double-check your `.env` values.

### 6. Keep both services running with tmux

If you want both services in one `tmux` session, run the same commands in separate panes:

```bash
# Start or resume a tmux session
tmux new -s opencode

# In pane 1: start the opencode server
opencode serve --print-logs

# Split the window (Ctrl+b, ")
# In pane 2: start the bot
uv run opencode-telegram
```

Now detach from tmux (`Ctrl+b, d`) — both services keep running. Reattach later with `tmux a -t opencode`.

### 7. Use the bot

Open Telegram, find your bot (the name you chose in step 1), and send:

```
/start
```

You'll see a control panel with buttons. From here you can create sessions, send prompts, switch agents, and more — all from your phone.

> **No Tailscale, VPN, or public IP needed.** The bot connects *outbound* to Telegram's servers, so it works with any internet connection. Telegram handles the message relay between your phone and the bot — you don't need to expose your machine to the internet.

## Features

### Telegram commands

| Input | Action |
|---|---|
| `/start` | Show the control panel |
| Any text message | Send as a prompt to the current session |
| Any opencode native command | See supported native commands below |
| Callback buttons | Navigate agents, models, sessions interactively |

### Supported opencode native commands

These opencode native commands work as Telegram slash commands (e.g. `/new`, `/sessions`):

| Command | Action |
|---|---|
| `/new` | Start a new session |
| `/clear` | Clear the current session |
| `/sessions` | List and switch between sessions |
| `/resume` or `/continue` | Resume a previous session |
| `/agents` | Select an AI agent |
| `/models` | Select a model provider/model |
| `/compact` or `/summarize` | Compact / summarize the current session |
| `/help` | Show available commands |
| `/init` | Run guided AGENTS.md setup |
| `/share` | Share the current session |
| `/unshare` | Unshare the current session |
| `/undo` | Undo the last message |
| `/redo` | Redo a previously undone message |
| `/exit`, `/quit`, or `/q` | End the current session |

### Unsupported TUI-only commands

These opencode TUI commands are **not** available via the Telegram bridge:

`/connect`, `/details`, `/editor`, `/export`, `/themes`, `/thinking`

### Dynamic commands from the server

Any commands registered on the opencode server (via plugins, custom tools, etc.) are automatically loaded at startup and available as Telegram slash commands. The bot fetches them from the server's `/command` endpoint on every launch.

## Configuration

All configuration lives in `.env`. See `.env.example` for all options:

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `TELEGRAM_ALLOWED_USER_ID` | Yes | — | Your Telegram user ID (single-user) |
| `OPENCODE_BASE_URL` | Yes | `http://127.0.0.1:4096` | opencode server URL |
| `OPENCODE_SERVER_USERNAME` | Yes | `opencode` | opencode API username |
| `OPENCODE_SERVER_PASSWORD` | Yes | — | opencode API password |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |
| `LOG_FILE` | No | `logs/opencode-telegram.log` | Log file path |
| `TELEGRAM_HTTP_LOGS` | No | `false` | Enable HTTP request logging |
| `TELEGRAM_EDIT_INTERVAL_SECONDS` | No | `1.0` | Minimum seconds between live stream edits |
| `EVENT_RECONNECT_INITIAL_SECONDS` | No | `1.0` | Initial SSE reconnect backoff |
| `EVENT_RECONNECT_MAX_SECONDS` | No | `30.0` | Maximum SSE reconnect backoff |

## Development

```bash
# Run tests
uv run pytest -v

# Type check (strict mode)
uv run mypy

# Lint
uv run ruff check .

# All checks in one go
uv run pytest -v && uv run mypy && uv run ruff check .
```

## Architecture

- **Single-user**: Only `TELEGRAM_ALLOWED_USER_ID` is authorized
- **Stateless HTTP**: Talks to opencode via its REST API (no WebSocket)
- **In-memory state**: Per-chat session, agent, and model selection kept in memory (async-locked `SessionState`)
- **SSE streaming**: A single shared SSE consumer parses `message.part.updated` events and streams assistant text back to Telegram (one message, edited ~1/sec)
- **Permission prompts**: `permission.updated` events are surfaced as inline Allow/Deny buttons in Telegram
- **All polls, no webhooks**: Uses Telegram polling (simple, no public endpoint needed)

## License

MIT — see [LICENSE](LICENSE) for details.

Copyright (c) 2025-2026 Joao Marcos Visotaky Junior
