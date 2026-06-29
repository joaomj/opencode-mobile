---
title: Telegram SSE parser mismatch with OpenCode instance event stream
status: resolved
created: 2026-06-28
---

## Summary

The Telegram bot's SSE event parser expects events wrapped in a `{"payload": {...}}`
envelope, but OpenCode's `/event` SSE endpoint emits events directly as
`{"id":"evt_42","type":"session.idle.1","properties":{...}}` — no `payload` wrapper.

This means every SSE event is silently dropped by the parser (`parse_event_line_with_id`
returns `(None, None)`), so the bot waits for the full 120s timeout before falling back
to polling. OpenCode itself finishes work in ~31s, so the user sees a 90s avoidable stall.

## Steps to Reproduce

1. Start opencode server with `opencode serve --print-logs`
2. Start bot with `uv run opencode-telegram`
3. Send a Telegram message to the bot
4. Observe logs: no `opencode event type=...` lines appear during streaming
5. After ~120s, logs show fallback polling kicks in and the answer arrives
6. OpenCode logs show work completed in ~31s

## Expected Behavior

- SSE events from `/event` are parsed immediately
- Bot relays event-driven updates in real time (no 120s stall)
- Fallback polling is a safety net, not the primary delivery path

## Actual Behavior

- `parse_event_line_with_id` extracts `outer.get("payload", {})` which is `{}`
  on direct-form events
- `parse_event_payload({})` returns `None`
- Logs show no `opencode event type=...` during streaming
- Bot waits 120s for SSE timeout, then uses fallback polling
- OpenCode work completes in ~31s; user waits ~91s extra

## Environment

- opencode 1.17.11 (Homebrew)
- opencode-mobile 0.1.0
- Python 3.11+, uv
- macOS (darwin)

## Affected Areas

- `src/opencode_telegram/opencode_client.py:275-283` — `parse_event_line`
- `src/opencode_telegram/opencode_client.py:286-296` — `parse_event_line_with_id`
- `src/opencode_telegram/config.py:36` — `opencode_request_timeout_seconds` default (120s)

## Possible Fixes

### A. Parser fix (recommended)

Make both `parse_event_line` and `parse_event_line_with_id` accept both forms:
- Direct: `{"id":"evt_42","type":"...","properties":{...}}`
- Wrapped: `{"payload": {"id":"evt_42","type":"...","properties":{...}}}`

Reduce `opencode_request_timeout_seconds` from `120s` to `60s` so even the fallback
path completes faster.

### B. Switch to `/api/event` endpoint

Migrate to OpenCode's v2 `/api/event` SSE endpoint. Larger change; more resilient
long-term but higher risk for a targeted fix.

## Implemented Fix

- Added `_unwrap_sse_payload(outer)` helper that accepts both wrapped (`{"payload": {...}}`)
  and direct (`{"type":..., "properties":...}`) SSE event shapes.
- Updated `parse_event_line` and `parse_event_line_with_id` to use `_unwrap_sse_payload`
  instead of always requiring the `payload` wrapper.
- Reduced `opencode_request_timeout_seconds` default from `120s` to `60s` so the fallback
  polling path completes faster even without SSE.
- Added 17 new regression tests:
  - 16 in `test_event_parser.py`: direct-form parsing, both-forms equivalence,
    direct-form versioned types
  - 1 in `test_event_consumer.py`: parse + route integration for direct-form SSE
  - 1 in `test_config.py`: timeout default is `60.0`
