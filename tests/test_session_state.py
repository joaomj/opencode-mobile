from opencode_telegram.session_state import SessionState


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
