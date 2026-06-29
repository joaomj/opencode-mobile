# Telegram Bridge: Thin Architecture Spec

## Principles

1. **The opencode server is the only execution authority.** Bridge never makes execution decisions.
2. **User input passes through unmodified.** No agent/model/variant injected by the bridge.
3. **No answer reconstruction.** The bridge delivers server output as-is — never synthesises, polls fallbacks, or resends old messages.
4. **Single source of truth.** The opencode server logs + sqlite are the execution truth. The bridge logs transport only.
5. **Every script/module ≤ 300 lines.** (Coding best practices rule.)
6. **Remove unused code.** `DeliveryManager` is already dead; `RunManager`, `opencode_db`, `event_consumer` are all replaced.

## Current Problems

### Broken command forwarding
The `Command` model (`opencode_client.py:21-28`) discards `agent`, `model`, `template` from the server's `/command` response. When dispatching a custom command like `/commit`, the bridge re-injects its own locally-selected agent/model/variant instead of using the command's own metadata (`bot.py:485-519`).

### Dead code paths
`DeliveryManager` (`delivery.py`) has full test coverage but is **never wired in production** (`bot.py:260-267` only passes `runmgr.handle_event` as the event callback).

### Over-engineered delivery
The current stack uses:
- SSE for message streaming
- Event replay from opencode sqlite for reconnection safety
- In-memory partial-text accumulation per run
- Timeout fallback that polls recent messages and can resend stale output
- Per-session log files

The server's synchronous endpoints (`POST /session/{id}/message`, `POST /session/{id}/command`) **block until the assistant finishes and return the complete final message**. The entire async/SSE/replay/delivery stack is unnecessary.

### Oversized files
| File | Lines | Limit |
|------|-------|-------|
| `bot.py` | 1063 | ≤300 |
| `opencode_client.py` | 555 | ≤300 |

Both must be split.

---

## Target Architecture

Two concurrent asyncio tasks, no dependencies between them:

- **Main handler** — receives Telegram input, calls sync REST endpoint, blocks until full response, delivers final answer.
- **Permission poller** — every 2s calls `GET /permission`, checks for pending requests matching active sessions, shows Telegram Allow/Deny buttons.

### Request flow diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│  Telegram Bot                                                       │
│                                                                     │
│  ┌─ Task 1: handle_message / handle_slash_command ───────────────┐  │
│  │                                                               │  │
│  │  User sends text or /commit                                   │  │
│  │    │                                                          │  │
│  │    ├─ 1. reply "working..."                                   │  │
│  │    │                                                          │  │
│  │    ├─ text:                                                   │  │
│  │    │    POST /session/{id}/message     ────────────► opencode  │  │
│  │    │    { parts: [{type:"text", text}] }       (blocks)       │  │
│  │    │                                                          │  │
│  │    ├─ /cmd:                                                   │  │
│  │    │    POST /session/{id}/command     ────────────► opencode  │  │
│  │    │    { command, arguments }                 (blocks)       │  │
│  │    │                                                          │  │
│  │    ├─ 3. deliver response ←────────────────── sync response  │  │
│  │    └─ done                                                    │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ Task 2: permission_poller (periodic, independent) ───────────┐  │
│  │                                                               │  │
│  │  every 2s: GET /permission ───────────────────────► opencode  │  │
│  │    │                                           ← permission[] │  │
│  │    ├─ for each request where sessionID ∈ active sessions:     │  │
│  │    │   if request.id not already tracked:                     │  │
│  │    │     send Telegram Allow/Deny buttons                     │  │
│  │    │     store requestID in permission_registry               │  │
│  │    └─ done                                                    │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ Task 3: Telegram callback handler ───────────────────────────┐  │
│  │                                                               │  │
│  │  User clicks Allow or Deny                                    │  │
│  │    │                                                          │  │
│  │    └─ POST /permission/{requestID}/reply ───────► opencode    │  │
│  │         { reply: "once"|"always"|"reject" }  ◄──── unblocks   │  │
│  │                                          sync handler         │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌─ Persistent data (small) ─────────────────────────────────────┐  │
│  │  BridgeDB: chat_id → session_id  (survives restarts)           │  │
│  │  PermissionRegistry: short_id → { sessionID, requestID }       │  │
│  │                         (in-memory, per chat)                  │  │
│  │  Last delivered message ID: per session dedupe                 │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## What Gets Removed

| Component | File(s) | Why |
|-----------|---------|-----|
| RunManager | `run_manager.py` | Replaced by sync endpoint blocking |
| DeliveryManager | `delivery.py` | Dead code; never wired in production |
| opencode sqlite dependency | `opencode_db.py` + config | No more event replay |
| SSE consumer | `event_consumer.py` | Replaced by `GET /permission` polling |
| Event replay logic | `event_consumer.py:102-220` | No reconnection needed |
| Per-session log files | `bot.py:147-173` (`SessionFileHandler`) | Single bridge transport log |
| Agent/model/reasoning selectors | native commands, callback handlers, `SessionState` fields | Bridge no longer selects these |
| Bridge-side agent/model/variant resolution | `bot.py:485-519` | Server is the authority |
| Timeout fallback that resends old messages | `run_manager.py:219-245` | Never synthesise answers |
| Fallback poll for assistant messages | `bot.py:383-421` (`_poll_for_assistant_message`) | Sync endpoints deliver final answer directly |
| `send_prompt_async` | `opencode_client.py` | No longer used |
| `send_command_async` | `opencode_client.py` | No longer used |
| `POST /session/{id}/permissions/{permissionID}` | `opencode_client.py` | Use `POST /permission/{requestID}/reply` instead |

---

## What Gets Kept (Minimal)

| Component | Notes |
|-----------|-------|
| Auth check (`telegram_allowed_user_id`) | Only Telegram guard needed |
| Chat → session mapping (`BridgeDB`) | Persists across restarts |
| Multi-session commands | `/new`, `/sessions`, `/resume` through sync endpoints |
| Server command auto-discovery | At startup from `GET /command` |
| Permission buttons + callbacks | Via permission poller, no SSE |
| One daily bridge transport log | Single file, no per-session split |

---

## Permission Handling

Discovery is via REST polling, not SSE. This was confirmed by inspecting the opencode server source and verifying against the running server:

```
GET /permission
  → PermissionRequest[]
     { id, sessionID, permission, patterns, metadata, always,
       tool?: { messageID, callID } }

POST /permission/{requestID}/reply
  body: { reply: "once" | "always" | "reject", message?: string }
  → boolean
```

The `GET /permission` endpoint returns all pending permission requests across all sessions. It is already live at the server root — no version prefix, no SSE dependency. The old `POST /session/{id}/permissions/{permissionID}` is deprecated in favour of the new REST endpoint.

**Flow:**
1. User sends `/commit`
2. Bridge calls sync `/session/{id}/command`, handler blocks
3. Server hits an `"ask"` permission → creates a permission request
4. Background permission poller calls `GET /permission`, finds the new request
5. Bridge sends Telegram Allow/Deny buttons for that request
6. User clicks Allow/Deny
7. Telegram callback calls `POST /permission/{requestID}/reply { reply: "once" }`
8. Server unblocks → continues processing → returns final response
9. Bridge delivers response

**Edge cases:**
- Permission already timed out server-side before the poller saw it → button does nothing; user retries the command
- User has Telegram window closed when permission arrives → missed; user retries
- Multiple pending permissions for the same session → dedicated buttons per request

---

## Command Model Fix

**Current** (`opencode_client.py:21-28`):
```python
class Command(BaseModel):
    name: str
    description: str = ""
    source: str = ""
```

**Change** — preserve server metadata:
```python
class Command(BaseModel):
    name: str
    description: str = ""
    source: str = ""
    agent: str | None = None
    model: str | None = None
```

This allows the server's command definitions (e.g. `/commit` has `model: opencode/deepseek-v4-flash-free`) to flow through without bridge override.

---

## Dispatch Changes

### For text prompts (current `handle_text`)

| Before | After |
|--------|-------|
| Resolve agent/model/variant from `SessionState` | Pass `agent=None, model=None` |
| Call `send_prompt_async()` | Call `send_message()` (sync) |
| `RunManager` tracks the run | No run tracking |
| SSE delivers streaming parts | Sync returns complete message |
| Fallback poll resends old messages | No fallback logic |

**Request body:**
```json
{
  "parts": [{"type": "text", "text": "<exact user text>"}]
}
```

No `agent`, no `model`, no `variant` keys.

### For slash commands (current `_handle_slash_command_with_correlation`)

| Before | After |
|--------|-------|
| Resolve agent/model/variant from `SessionState` | Pass `agent=None, model=None` |
| Call `send_command_async()` | Call `run_command()` (sync) |
| Bridge injects its own model | Let server use command's own model |

**Request body:**
```json
{
  "command": "commit",
  "arguments": ""
}
```

No `agent`, no `model` keys. If the server command has its own `model` field, it is respected server-side.

### For native session commands (current `_run_native_session_command`)

Already uses the sync `run_command()` endpoint — this stays unchanged except the `agent`/`model` overrides are removed.

---

## File Splitting Plan

All new files are ≤300 lines.

### `opencode_client.py` (555 → split into 2 files)
- `models.py` — all Pydantic models (`Command`, `Session`, `Message`, `Part`, `CommandRequest`, `PermissionRequest`, etc.)
- `client.py` — `OpendcodeClient` class (HTTP transport, all REST methods)

### `bot.py` (1063 → split into 4 files)
- `handlers.py` — Telegram handlers (`handle_text`, `handle_slash_command`, `handle_start`, `handle_callback`)
- `logging_config.py` — Logging setup, formatters, handlers
- `startup.py` — `run_bot()`, `load_opencode_commands_resilient()`, `build_telegram_commands()`
- `permissions.py` — Permission poller, Telegram button builders, callback handler

### New file
- `poller.py` — Periodic permission poller task (calls `GET /permission`, dedupes, dispatches buttons)

---

## Permission Poller Design

Single asyncio task, no SSE:

```python
async def permission_poller(
    client: OpencodeClient,
    state: SessionState,
    application: Application,
    runtime: RuntimeConfig,
) -> None:
    while True:
        await asyncio.sleep(2.0)  # or runtime.permission_poll_interval_seconds

        requests = await client.list_pending_permissions()
        if not requests:
            continue

        for req in requests:
            chat_id = state.get_chat_for_session(req.sessionID)
            if chat_id is None:
                continue
            if state.has_tracked_permission(req.id):
                continue

            short_id = state.register_permission(chat_id, req.id)
            await application.bot.send_message(
                chat_id=chat_id,
                text=f"Permission request: {req.permission}",
                reply_markup=build_permission_keyboard(short_id),
            )
```

On callback:
```python
async def _handle_permission_callback(data: str, ...):
    parsed = parse_permission_callback(data)  # pa:/pd:/par:/pdr: prefix
    registration = state.get_permission(parsed.short_id)
    await client.reply_permission(
        request_id=registration.request_id,
        reply=parsed.response,  # "once" | "always" | "reject"
    )
    state.remove_tracked_permission(registration.request_id)
```

**Dedupe**: `req.id` is tracked in `SessionState._permission_registry`. Once the user responds, the entry is removed. If the server has already timed out the request, the `POST /permission/{id}/reply` will return a 404, which is handled gracefully.

---

## Logging Simplification

- Remove `SessionFileHandler` (per-session log files) — only one bridge log
- Remove `SessionFilter` (no longer injects `session_id` into log records)
- Keep `CorrelationFormatter` (still useful for tracing)
- Log format: `timestamp LEVEL name cid=X message`
- Keep one daily rotating log file
- All diagnostic truth comes from opencode server logs + sqlite

---

## `SessionState` Trimming

Remove:
- `_agent_by_chat`, `_model_by_chat`, `_variant_by_chat`
- `set_agent_async`, `get_agent_async`, `set_model_async`, `get_model_async`, `get_variant_async`, `set_variant_async`
- `register_model_option_async`, `get_model_option_async`
- All model option registration

Keep:
- `_active_by_chat` (chat → session mapping)
- `_permission_registry` (short_id → { sessionID, requestID } for callback routing)
- `_last_delivered_assistant_message_ids` (not needed for sync flow, but harmless)

---

## Migration Steps (Ordered)

### Phase 1 — Code structure
1. Split `opencode_client.py` into `models.py` + `client.py`
2. Split `bot.py` into `handlers.py` + `logging_config.py` + `startup.py` + `permissions.py`
3. Remove dead code: `DeliveryManager`, `opencode_db`, `RunManager`, `event_consumer`
4. Add `poller.py` for periodic `GET /permission`

### Phase 2 — Sync endpoint migration
5. Fix `Command` model to preserve `agent`, `model`
6. Rewrite `handle_text` to use `send_message()` (sync) — no agent/model/variant
7. Rewrite slash command dispatch to use `run_command()` (sync) — no agent/model/variant
8. Remove `send_prompt_async`, `send_command_async` client methods

### Phase 3 — Permission reshape
9. Wire permission poller into `run_bot()`
10. Rewrite `_handle_permission_callback` to use `POST /permission/{requestID}/reply`
11. Implement `client.list_pending_permissions()` and `client.reply_permission()`
12. Remove old permission event handling (no more SSE)

### Phase 4 — UI and state cleanup
13. Remove agent/model/reasoning native commands and callback handlers
14. Trim `SessionState` to chat→session mapping + permission registry
15. Remove `SessionFileHandler` and `SessionFilter`

### Phase 5 — Polish
16. Remove `_poll_for_assistant_message` fallback
17. Update README architecture section
18. Run full test suite: `uv run pytest -v && uv run mypy && uv run ruff check .`

---

## Risks and Open Questions

| Risk | Mitigation |
|------|------------|
| Sync endpoint blocks >60s for long prompts | Initial "working..." message sent before blocking. Telegram polling has no hard timeout for async handlers. If needed, add a per-call timeout. |
| Permission poller interval too aggressive | Default to 2s. Make configurable. |
| Permission already expired when user clicks | `POST /permission/{id}/reply` returns 404 → show "permission request expired" (already handled today). |
| Session simultaneously claimed by TUI | The opencode server uses the same REST API for all clients. If TUI sends a prompt to the same session, one client wins. This is inherent to shared session access and not a bridge problem. |
| `POST /session/{id}/message` returns 404 for sessions that don't accept prompts | Will produce an HTTP error visible to the user. The bridge reports the error as-is. |

**Verified by server source inspection (`GET /permission` exists at root, returns `PermissionRequest[]`):**
- No SSE needed for permissions
- No SSE needed for message delivery
- No SSE at all
- The server already has a full REST API for every feature the bridge needs

---

## Testing Strategy

- Unit tests for `Command` model (metadata preservation)
- Unit tests for sync message/command dispatch (request body correctness)
- Unit tests for permission poller dedupe
- Unit tests for permission callback handling
- Integration test: send a text through the sync endpoint, verify the returned `Message`
- Integration test: send a command through the sync endpoint, verify no agent/model injected
- Keep existing test coverage for `BridgeDB`

Tests that can be removed:
- `test_delivery.py`, `test_delivery_integration.py` (dead code)
- `test_fallback.py` (no more fallback poll)
- Event consumer tests (no more SSE)

---

## Completion Criteria

- [ ] All Python files ≤300 lines
- [ ] No RunManager, DeliveryManager, opencode_db, event_consumer dependencies
- [ ] Prompt dispatch sends only `parts: [{type: "text", text: ...}]`
- [ ] Command dispatch sends only `{command, arguments}`, no agent/model
- [ ] Command model preserves server metadata
- [ ] Permission poller uses `GET /permission` + `POST /permission/{id}/reply`
- [ ] No SSE anywhere
- [ ] Single bridge transport log (no per-session files)
- [ ] No agent/model/reasoning UI in Telegram
- [ ] `ruff check .` passes
- [ ] `mypy` passes
- [ ] All existing permission-related tests pass
