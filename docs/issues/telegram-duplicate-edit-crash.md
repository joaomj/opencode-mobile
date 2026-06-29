---
title: Unhandled BadRequest "Message is not modified" crashes streaming handler
status: open
created: 2026-06-28
---

## Summary

When `render_stream` edits the Telegram progress message with identical content,
Telegram API returns `400 BadRequest: Message is not modified`. This exception is
unhandled, so the entire `handle_text` handler crashes and the bot never sends the
final answer — even though OpenCode completed its work successfully.

## Steps to Reproduce

1. Start opencode server and Telegram bot.
2. Send a prompt via Telegram.
3. The bot creates a progress message and subscribes to SSE events.
4. SSE events arrive and `render_stream` calls `edit_text` on the progress message.
5. If the edited content is identical to the current content (e.g. two rapid
   `message.part.updated` events with no new text delta, or a status update that
   produces the same status string), Telegram returns a `400 Bad Request`.
6. The unhandled `BadRequest` propagates up through `handle_text`, which exits.
7. The bot never sends the final assistant reply.

## Expected Behavior

- Duplicate progress edits are silently ignored (either skipped before the API call
  or caught and handled).
- `render_stream` continues processing subsequent events.
- The final assistant reply is always sent.

## Actual Behavior

```
telegram.error.BadRequest: Message is not modified: specified new message content
and reply markup are exactly the same as a current content and reply markup of the
message
```

The exception propagates uncaught from `_edit_or_retry` → `apply_delta` →
`render_stream` → `handle_text`. The handler exits, the bot reports no answer,
and the user sees a hanging request.

## Environment

- opencode-mobile 0.1.0
- python-telegram-bot 22.x
- Python 3.11
- macOS (darwin)

## Affected Areas

- `src/opencode_telegram/streaming.py:150-161` — `_edit_or_retry` only catches
  `RetryAfter`, not `BadRequest`.
- `src/opencode_telegram/streaming.py:60-71` — `apply_delta` calls
  `_edit_or_retry` without protecting against duplicate content.
- `src/opencode_telegram/bot.py:318-323` — `handle_text` calls `render_stream`
  without a catch for delivery-level errors.

## Possible Fixes

### Option A: Catch BadRequest in _edit_or_retry (minimal)

Add `except BadRequest as exc` in `_edit_or_retry`. If the error message contains
`"Message is not modified"`, log and skip. Re-raise all other `BadRequest` errors.

### Option B: Track last edited text in _RenderState

Store the last successfully edited text in `_RenderState`. Before calling
`_edit_or_retry`, compare — if identical, skip the edit entirely. This prevents
redundant API calls and avoids the error condition at the source.

### Option C: Switch to polling-only

Remove SSE streaming entirely and poll `/message` for the final response. Avoids
all streaming-related Telegram edit edge cases at the cost of losing real-time
progress updates.

## Implemented Fix

### Approach: Option B + defensive Option A

Two-layer defence applied in `src/opencode_telegram/streaming.py`:

1. **Skip identical edits before the API call** (`_RenderState.apply_delta`, line 68-71).
   A new field `last_progress_text` tracks the last fully-formatted progress string
   (prefix + buffer + status). Before calling `_edit_or_retry`, the next display text
   is computed and compared — if identical, the edit is skipped entirely (the throttle
   slot is still consumed via `last_edit = now`).

2. **Catch `BadRequest` with "Message is not modified"** (`_edit_or_retry`, line 163-165).
   Any `BadRequest` whose string representation contains `"Message is not modified"`
   is silently caught and returned. All other `BadRequest` errors (e.g. message too
   long, no rights to edit) still propagate. This covers edge cases where Telegram
   normalises formatting differently than our string comparison.

### Files changed

- `src/opencode_telegram/streaming.py` — add `last_progress_text` to `_RenderState`,
  skip-identical-text check in `apply_delta`, `BadRequest` handler in `_edit_or_retry`.
- `tests/test_streaming.py` — add `raise_on_next_edit` to `FakeProgress`; three new
  tests:
  - `test_render_stream_skips_duplicate_progress_edit` (Option B)
  - `test_render_stream_survives_duplicate_edit_bad_request` (Option A)
  - `test_render_stream_raises_other_bad_request` (non-"not modified" still crashes)
- `docs/issues/telegram-duplicate-edit-crash.md` — this entry.
