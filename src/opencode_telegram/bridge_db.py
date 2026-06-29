import logging
import sqlite3
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)

DEFAULT_BRIDGE_DB_PATH = Path.home() / ".local" / "state" / "opencode-telegram" / "bridge.db"

_CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS chat_active ("
    "chat_id INTEGER PRIMARY KEY,"
    "session_id TEXT NOT NULL,"
    "updated INTEGER NOT NULL"
    ")"
)
_CREATE_SESSION_INDEX = (
    "CREATE INDEX IF NOT EXISTS chat_active_session_idx ON chat_active (session_id)"
)
_UPSERT_ACTIVE = (
    "INSERT INTO chat_active (chat_id, session_id, updated) VALUES (?, ?, ?) "
    "ON CONFLICT(chat_id) DO UPDATE SET session_id = excluded.session_id, "
    "updated = excluded.updated"
)
_GET_ACTIVE = "SELECT session_id FROM chat_active WHERE chat_id = ?"
_GET_CHAT_FOR_SESSION = "SELECT chat_id FROM chat_active WHERE session_id = ?"
_CLEAR_ACTIVE = "DELETE FROM chat_active WHERE chat_id = ?"
_LIST_ACTIVE = "SELECT chat_id, session_id FROM chat_active ORDER BY chat_id"
_DROP_TABLE_FOR_OWNERSHIP = "DELETE FROM chat_active WHERE session_id = ? AND chat_id != ?"


class BridgeDB:
    """Persists per-chat active opencode session across bot restarts."""

    def __init__(self, path: Path | str = DEFAULT_BRIDGE_DB_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_SESSION_INDEX)
        self._conn.commit()

    def set_active(self, chat_id: int, session_id: str) -> None:
        now = int(time.time())
        self._conn.execute(_UPSERT_ACTIVE, (chat_id, session_id, now))
        self._conn.execute(_DROP_TABLE_FOR_OWNERSHIP, (session_id, chat_id))
        self._conn.commit()

    def get_active(self, chat_id: int) -> str | None:
        row = self._conn.execute(_GET_ACTIVE, (chat_id,)).fetchone()
        if row is None:
            return None
        value: str | None = row["session_id"]
        return value

    def get_chat_for_session(self, session_id: str) -> int | None:
        row = self._conn.execute(_GET_CHAT_FOR_SESSION, (session_id,)).fetchone()
        if row is None:
            return None
        return int(row["chat_id"])

    def clear_active(self, chat_id: int) -> None:
        self._conn.execute(_CLEAR_ACTIVE, (chat_id,))
        self._conn.commit()

    def list_active(self) -> list[tuple[int, str]]:
        rows = self._conn.execute(_LIST_ACTIVE).fetchall()
        return [(int(row["chat_id"]), row["session_id"]) for row in rows]

    def close(self) -> None:
        self._conn.close()
