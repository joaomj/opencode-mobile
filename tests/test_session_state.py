
import pytest

from opencode_telegram.bridge_db import BridgeDB
from opencode_telegram.session_state import PermissionRegistration, SessionState


@pytest.fixture
def bridge_db(tmp_path):
    db = BridgeDB(tmp_path / "bridge.db")
    yield db
    db.close()


def test_new_session_becomes_active_for_chat() -> None:
    state = SessionState()

    state.set_active(chat_id=42, session_id="ses_1")

    assert state.get_active(chat_id=42) == "ses_1"


def test_switching_session_preserves_per_chat_isolation() -> None:
    state = SessionState()

    state.set_active(chat_id=1, session_id="ses_a")
    state.set_active(chat_id=2, session_id="ses_b")
    state.set_active(chat_id=1, session_id="ses_c")

    assert state.get_active(chat_id=1) == "ses_c"
    assert state.get_active(chat_id=2) == "ses_b"


def test_agent_selection_is_per_chat() -> None:
    state = SessionState()

    state.set_agent(chat_id=1, agent="build")
    state.set_agent(chat_id=2, agent="plan")

    assert state.get_agent(chat_id=1) == "build"
    assert state.get_agent(chat_id=2) == "plan"


def test_model_selection_is_per_chat() -> None:
    state = SessionState()

    state.set_model(chat_id=1, provider_id="anthropic", model_id="claude-sonnet")
    state.set_model(chat_id=2, provider_id="openai", model_id="gpt-5")

    assert state.get_model(chat_id=1).provider_id == "anthropic"
    assert state.get_model(chat_id=1).model_id == "claude-sonnet"
    assert state.get_model(chat_id=2).provider_id == "openai"
    assert state.get_model(chat_id=2).model_id == "gpt-5"


@pytest.mark.asyncio
async def test_event_queue_registered_per_session() -> None:
    state = SessionState()

    queue = await state.register_event_queue_async("s1")

    assert queue is await state.get_event_queue_async("s1")
    assert queue.maxsize == 0


@pytest.mark.asyncio
async def test_event_queue_is_replaced_on_re_register() -> None:
    state = SessionState()

    first = await state.register_event_queue_async("s1")
    second = await state.register_event_queue_async("s1")

    assert first is not second
    assert await state.get_event_queue_async("s1") is second


@pytest.mark.asyncio
async def test_event_queue_unregistered() -> None:
    state = SessionState()

    await state.register_event_queue_async("s1")
    await state.unregister_event_queue_async("s1")

    assert await state.get_event_queue_async("s1") is None


@pytest.mark.asyncio
async def test_event_queue_routing_to_session() -> None:
    state = SessionState()

    queue = await state.register_event_queue_async("s1")
    await queue.put("event")

    assert queue.get_nowait() == "event"


@pytest.mark.asyncio
async def test_permission_registry_returns_short_id() -> None:
    state = SessionState()

    short_id = await state.register_permission_async(
        session_id="s1", permission_id="perm1"
    )

    assert isinstance(short_id, str)
    assert len(short_id) > 0


@pytest.mark.asyncio
async def test_permission_registry_looks_up_by_short_id() -> None:
    state = SessionState()

    short_id = await state.register_permission_async(
        session_id="s1", permission_id="perm1"
    )

    assert await state.get_permission_async(short_id) == PermissionRegistration(
        session_id="s1", permission_id="perm1"
    )


@pytest.mark.asyncio
async def test_permission_registry_returns_none_for_unknown_short_id() -> None:
    state = SessionState()

    assert await state.get_permission_async("missing") is None


@pytest.mark.asyncio
async def test_persisted_active_session_survives_new_state_recreated(
    bridge_db: BridgeDB,
) -> None:
    first = SessionState(bridge_db=bridge_db)
    await first.set_active_async(chat_id=42, session_id="ses_persisted")

    second = SessionState(bridge_db=bridge_db)
    assert await second.get_active_async(chat_id=42) == "ses_persisted"
    assert await second.get_chat_for_session_async("ses_persisted") == 42


@pytest.mark.asyncio
async def test_persisted_overwrite_clears_other_chat_owner(bridge_db: BridgeDB) -> None:
    state = SessionState(bridge_db=bridge_db)
    await state.set_active_async(chat_id=1, session_id="ses_x")
    await state.set_active_async(chat_id=2, session_id="ses_x")

    assert await state.get_active_async(chat_id=1) is None
    assert await state.get_active_async(chat_id=2) == "ses_x"
    assert await state.get_chat_for_session_async("ses_x") == 2


@pytest.mark.asyncio
async def test_in_memory_mode_still_works_without_bridge() -> None:
    state = SessionState()

    await state.set_active_async(chat_id=42, session_id="ses_1")

    assert await state.get_active_async(chat_id=42) == "ses_1"
    assert await state.get_chat_for_session_async("ses_1") == 42


# ── Delivered assistant message tracking ─────────────────────────────────


def test_last_delivered_assistant_message_defaults_to_none() -> None:
    state = SessionState()
    assert state.get_last_delivered_assistant_message_id("s1") is None


def test_last_delivered_assistant_message_round_trip() -> None:
    state = SessionState()
    state.set_last_delivered_assistant_message_id("s1", "m42")
    assert state.get_last_delivered_assistant_message_id("s1") == "m42"


def test_last_delivered_assistant_message_overwrites() -> None:
    state = SessionState()
    state.set_last_delivered_assistant_message_id("s1", "m1")
    state.set_last_delivered_assistant_message_id("s1", "m2")
    assert state.get_last_delivered_assistant_message_id("s1") == "m2"


def test_last_delivered_assistant_message_is_session_scoped() -> None:
    state = SessionState()
    state.set_last_delivered_assistant_message_id("s1", "m1")
    state.set_last_delivered_assistant_message_id("s2", "m2")
    assert state.get_last_delivered_assistant_message_id("s1") == "m1"
    assert state.get_last_delivered_assistant_message_id("s2") == "m2"


@pytest.mark.asyncio
async def test_last_delivered_assistant_message_async_defaults_to_none() -> None:
    state = SessionState()
    assert await state.get_last_delivered_assistant_message_id_async("s1") is None


@pytest.mark.asyncio
async def test_last_delivered_assistant_message_async_round_trip() -> None:
    state = SessionState()
    await state.set_last_delivered_assistant_message_id_async("s1", "m42")
    assert await state.get_last_delivered_assistant_message_id_async("s1") == "m42"
