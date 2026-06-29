from pathlib import Path

import pytest

from opencode_telegram.bridge_db import BridgeDB


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "bridge.db"


def test_get_active_returns_none_for_missing_chat(db_path: Path) -> None:
    db = BridgeDB(db_path)
    assert db.get_active(chat_id=42) is None
    db.close()


def test_set_active_upserts(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=42, session_id="ses_1")
    assert db.get_active(chat_id=42) == "ses_1"
    db.close()


def test_set_active_overwrites_previous_session_per_chat(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=42, session_id="ses_1")
    db.set_active(chat_id=42, session_id="ses_2")
    assert db.get_active(chat_id=42) == "ses_2"
    db.close()


def test_per_chat_isolation(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=1, session_id="ses_a")
    db.set_active(chat_id=2, session_id="ses_b")
    assert db.get_active(chat_id=1) == "ses_a"
    assert db.get_active(chat_id=2) == "ses_b"
    db.close()


def test_get_chat_for_session_reverse_lookup(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=42, session_id="ses_1")
    assert db.get_chat_for_session("ses_1") == 42
    assert db.get_chat_for_session("nope") is None
    db.close()


def test_get_chat_for_session_handles_overwrite(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=1, session_id="ses")
    db.set_active(chat_id=2, session_id="ses")
    assert db.get_chat_for_session("ses") == 2
    assert db.get_active(chat_id=1) is None
    db.close()


def test_clear_active_removes_chat(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=42, session_id="ses_1")
    db.clear_active(chat_id=42)
    assert db.get_active(chat_id=42) is None
    assert db.get_chat_for_session("ses_1") is None
    db.close()


def test_set_active_is_idempotent(db_path: Path) -> None:
    db = BridgeDB(db_path)
    for _ in range(3):
        db.set_active(chat_id=42, session_id="ses_1")
    assert db.get_active(chat_id=42) == "ses_1"
    db.close()


def test_persistence_across_reopen(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=42, session_id="ses_1")
    db.close()

    db2 = BridgeDB(db_path)
    assert db2.get_active(chat_id=42) == "ses_1"
    assert db2.get_chat_for_session("ses_1") == 42
    db2.close()


def test_starts_empty_table_schema_has_expected_columns(db_path: Path) -> None:
    db = BridgeDB(db_path)
    rows = db.list_active()
    assert rows == []
    db.close()


def test_list_active_returns_all_rows(db_path: Path) -> None:
    db = BridgeDB(db_path)
    db.set_active(chat_id=1, session_id="ses_a")
    db.set_active(chat_id=2, session_id="ses_b")
    rows = db.list_active()
    assert sorted(rows) == [(1, "ses_a"), (2, "ses_b")]
    db.close()
