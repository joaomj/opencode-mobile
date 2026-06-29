# Architecture — opencode-telegram

## Overview

`opencode-telegram` is a **thin transport bridge** between Telegram and a local
[opencode](https://opencode.ai) REST API. It has no execution authority — all
prompting, command execution, and decision-making lives on the opencode server.

```
┌──────────────┐    Telegram Bot API    ┌──────────────────┐    REST (localhost)    ┌──────────────┐
│  Telegram    │ ◄───────────────────── │  opencode-       │ ────────────────────► │  opencode    │
│  (your phone)│     getUpdates /        │  telegram        │  POST /session/{id}/   │  server      │
│              │     sendMessage         │                  │    message|command    │              │
│              │                        │  Permission      │  GET /permission      │              │
│              │                        │  poller (2s)     │  POST /permission/    │              │
│              │                        │                  │    {id}/reply         │              │
└──────────────┘                        └──────────────────┘                       └──────────────┘
```

## Core Design Principles

1. **Server is the only execution authority.** The bridge never makes execution
   decisions, never injects agent/model/variant, and never synthesises answers.
2. **User input passes through unmodified.** Text and commands are forwarded
   as-is to the server REST API.
3. **No answer reconstruction.** The bridge delivers server output as-is —
   no SSE, no event replay, no fallback polling, no message resend.
4. **Sync endpoints, not streaming.** `POST /session/{id}/message` and
   `POST /session/{id}/command` block until the server returns the complete
   final response. The entire async/SSE/delivery stack was removed.
5. **Permission via REST polling, not SSE.** A background task calls
   `GET /permission` every 2 seconds and surfaces pending requests as
   Telegram inline keyboard buttons (Allow / Allow + remember / Deny / Deny + remember).

## Source Layout

```
src/opencode_telegram/
  __init__.py            — Package init, exports, version
  __main__.py            — Entry point: `uv run opencode-telegram`
  _logging_context.py    — Correlation ID context var
  bridge_db.py           — SQLite persistence for chat→session mapping
  buttons.py             — Inline keyboard builders (control panel, sessions)
  client.py              — OpencodeClient: HTTP transport, all REST methods
  commands.py            — Slash command resolution
  config.py              — Settings + RuntimeConfig (pydantic-settings)
  format.py              — Telegram message truncation helpers
  handlers.py            — All Telegram update handlers
  logging_config.py      — Logging setup (file rotation, formatting)
  models.py              — Pydantic models (Message, Command, Session, Permission…)
  native_commands.py     — Native opencode commands supported via Telegram
  permission_handler.py  — Permission callback data parsing and keyboard building
  poller.py              — Background permission poller task
  session_state.py       — In-memory + BridgeDB session tracking
  startup.py             — run_bot(), handler wiring, poller creation
```

## Data Flow

### Text prompt or slash command

```
User sends text or /commit
  │
  ├─ handle_text() or handle_slash_command() in handlers.py
  │     │
  │     ├─ _ensure_session() → create or reuse session via POST /session
  │     │
  │     ├─ Send "working…" placeholder message
  │     │
  │     ├─ text:  POST /session/{id}/message  { parts: [{type:"text", text}] }
  │     ├─ /cmd:  POST /session/{id}/command  { command, arguments }
  │     │         (blocks until server returns final Message, up to timeout_seconds)
  │     │
  │     └─ Edit placeholder with response text
  │
  └─ Timeout (default 200s): show "error: request failed"
```

### Permission handling (concurrent)

```
Background poller (every 2s):
  GET /permission → PermissionRequest[]
    │
    └─ For each request where sessionID maps to a known chat_id:
         │
         ├─ Skip if already tracked (dedupe via request_id)
         ├─ Register short_id in SessionState._permissions
         └─ Send Telegram message with Allow/Deny inline keyboard

User clicks Allow / Deny:
  handle_callback() in handlers.py
    │
    ├─ Parse callback_data → { response, remember, short_id }
    ├─ Look up short_id → { session_id, request_id }
    ├─ Map response: allow→"once", allow+remember→"always", deny→"reject"
    ├─ POST /permission/{requestID}/reply  { reply: "once"|"always"|"reject" }
    └─ Edit button message to show result
```

## Key Components

### OpencodeClient (`client.py`)

HTTP client wrapping all opencode REST endpoints. Key methods:

| Method | Endpoint | Timeout |
|--------|----------|---------|
| `create_session()` | `POST /session` | default (200s) |
| `send_message()` | `POST /session/{id}/message` | override (200s) |
| `run_command()` | `POST /session/{id}/command` | override (200s) |
| `list_sessions()` | `GET /session` | default |
| `list_commands()` | `GET /command` | default |
| `list_pending_permissions()` | `GET /permission` | default |
| `reply_permission()` | `POST /permission/{id}/reply` | default |
| `abort_session()` | `POST /session/{id}/abort` | default |

### SessionState (`session_state.py`)

Manages chat→session mapping and permission tracking. Two layers:

- **BridgeDB** (SQLite, `bridge_db.py`): persists mapping across bot restarts
- **In-memory dicts** (`_chat_by_session`, `_permissions`): fast access, guarded by `asyncio.Lock`

### Permission Poller (`poller.py`)

Single `asyncio.Task` that polls `GET /permission` every 2s. Deduplicates by
`request_id` — once a permission is registered, it's skipped on subsequent polls.

### BridgeDB (`bridge_db.py`)

SQLite database at `~/.local/state/opencode-telegram/bridge.db`.
Single table `chat_active`: `(chat_id INTEGER PK, session_id TEXT, updated INTEGER)`.
Used to restore active session mapping when the bot restarts.

## Timeout Configuration

A single global timeout (`opencode_request_timeout_seconds`, default 200s) applies
to all outbound HTTP requests to the opencode server. This includes both regular
prompts and commands that may trigger permission prompts.

## Error Handling

- HTTP errors (4xx, 5xx) from the server are propagated to the user as Telegram
  messages via `raise_for_status()` → caught in handler try/except blocks.
- Permission reply 404 → "permission request expired" (user retries the command).
- Callback handler exceptions are caught and logged; the `getUpdates` offset is
  always advanced to prevent infinite retry loops.
- Startup retries connecting to opencode (configurable count/delay); degraded
  mode (no command menu) if server is unavailable.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token (required) |
| `TELEGRAM_ALLOWED_USER_ID` | — | Authorized Telegram user ID (required) |
| `OPENCODE_BASE_URL` | — | opencode server URL (required) |
| `OPENCODE_SERVER_USERNAME` | `opencode` | opencode API username |
| `OPENCODE_SERVER_PASSWORD` | — | opencode API password (required) |
| `OPENCODE_REQUEST_TIMEOUT_SECONDS` | `200.0` | Global HTTP timeout |
| `LOG_LEVEL` | `INFO` | Logging verbosity |
| `LOG_FILE` | `logs/opencode-telegram.log` | Log file path |
| `TELEGRAM_HTTP_LOGS` | `false` | Enable HTTP request logging |
| `BRIDGE_DB_PATH` | `~/.local/state/…/bridge.db` | BridgeDB path |
| `OPENCODE_STARTUP_RETRIES` | `5` | Server connection retries |
| `OPENCODE_STARTUP_RETRY_DELAY_SECONDS` | `2.0` | Delay between retries |

## Session Lifecycle

1. User sends any message → `_ensure_session()` checks BridgeDB for active session
2. If none → `POST /session` creates a new one → stored in BridgeDB + in-memory
3. All subsequent messages use same session until `/new` or `/exit`
4. Session persists in BridgeDB across bot restarts
5. `/abort` sends `POST /session/{id}/abort` to the server

## Permission Reply Values

| Button | `reply` value | Effect |
|--------|---------------|--------|
| Allow | `"once"` | Approve this one operation |
| Allow + remember | `"always"` | Approve and save rule for this session |
| Deny | `"reject"` | Reject the operation |
| Deny + remember | `"reject"` | Reject (remember flag is ignored for rejections) |
