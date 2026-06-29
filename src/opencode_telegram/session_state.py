import asyncio
from itertools import count

from pydantic import BaseModel

from opencode_telegram.bridge_db import BridgeDB


class PermissionRegistration(BaseModel):
    session_id: str
    request_id: str


class SessionState:
    def __init__(self, bridge_db: BridgeDB | None = None) -> None:
        self._bridge_db = bridge_db
        self._active_by_chat: dict[int, str] = {}
        self._permissions: dict[str, PermissionRegistration] = {}
        self._permission_counter = count(1)
        self._chat_by_session: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def get_active(self, chat_id: int) -> str | None:
        if self._bridge_db is not None:
            return self._bridge_db.get_active(chat_id)
        return self._active_by_chat.get(chat_id)

    def set_active(self, chat_id: int, session_id: str) -> None:
        if self._bridge_db is not None:
            self._bridge_db.set_active(chat_id=chat_id, session_id=session_id)
            self._chat_by_session[session_id] = chat_id
            return
        self._active_by_chat[chat_id] = session_id
        self._chat_by_session[session_id] = chat_id

    def get_chat_for_session(self, session_id: str) -> int | None:
        if self._bridge_db is not None:
            return self._bridge_db.get_chat_for_session(session_id)
        return self._chat_by_session.get(session_id)

    def register_permission(self, session_id: str, request_id: str) -> str:
        short_id = f"p{next(self._permission_counter)}"
        self._permissions[short_id] = PermissionRegistration(
            session_id=session_id,
            request_id=request_id,
        )
        return short_id

    def get_permission(self, short_id: str) -> PermissionRegistration | None:
        return self._permissions.get(short_id)

    def remove_permission(self, request_id: str) -> None:
        to_remove = [
            short_id
            for short_id, reg in self._permissions.items()
            if reg.request_id == request_id
        ]
        for short_id in to_remove:
            self._permissions.pop(short_id, None)

    def has_tracked_permission(self, request_id: str) -> bool:
        return any(
            reg.request_id == request_id
            for reg in self._permissions.values()
        )

    async def get_active_async(self, chat_id: int) -> str | None:
        async with self._lock:
            return self.get_active(chat_id)

    async def set_active_async(self, chat_id: int, session_id: str) -> None:
        async with self._lock:
            self.set_active(chat_id=chat_id, session_id=session_id)

    async def get_chat_for_session_async(self, session_id: str) -> int | None:
        async with self._lock:
            return self.get_chat_for_session(session_id=session_id)

    async def register_permission_async(self, session_id: str, request_id: str) -> str:
        async with self._lock:
            return self.register_permission(
                session_id=session_id,
                request_id=request_id,
            )

    async def get_permission_async(self, short_id: str) -> PermissionRegistration | None:
        async with self._lock:
            return self.get_permission(short_id=short_id)

    async def remove_permission_async(self, request_id: str) -> None:
        async with self._lock:
            self.remove_permission(request_id=request_id)
