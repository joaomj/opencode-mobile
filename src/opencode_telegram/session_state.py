import asyncio
from itertools import count

from pydantic import BaseModel, ConfigDict, Field


class ModelSelection(BaseModel):
    provider_id: str = Field(alias="providerID")
    model_id: str = Field(alias="modelID")

    model_config = ConfigDict(populate_by_name=True)


class SessionState:
    def __init__(self) -> None:
        self._active_by_chat: dict[int, str] = {}
        self._agent_by_chat: dict[int, str] = {}
        self._model_by_chat: dict[int, ModelSelection] = {}
        self._model_options: dict[str, ModelSelection] = {}
        self._model_option_counter = count(1)
        self._lock = asyncio.Lock()

    def get_active(self, chat_id: int) -> str | None:
        return self._active_by_chat.get(chat_id)

    def set_active(self, chat_id: int, session_id: str) -> None:
        self._active_by_chat[chat_id] = session_id

    def get_agent(self, chat_id: int) -> str | None:
        return self._agent_by_chat.get(chat_id)

    def set_agent(self, chat_id: int, agent: str) -> None:
        self._agent_by_chat[chat_id] = agent

    def get_model(self, chat_id: int) -> ModelSelection | None:
        return self._model_by_chat.get(chat_id)

    def set_model(self, chat_id: int, provider_id: str, model_id: str) -> None:
        self._model_by_chat[chat_id] = ModelSelection(providerID=provider_id, modelID=model_id)

    def register_model_option(self, provider_id: str, model_id: str) -> str:
        option_id = f"m{next(self._model_option_counter)}"
        self._model_options[option_id] = ModelSelection(providerID=provider_id, modelID=model_id)
        return option_id

    def get_model_option(self, option_id: str) -> ModelSelection | None:
        return self._model_options.get(option_id)

    async def get_active_async(self, chat_id: int) -> str | None:
        async with self._lock:
            return self.get_active(chat_id)

    async def set_active_async(self, chat_id: int, session_id: str) -> None:
        async with self._lock:
            self.set_active(chat_id=chat_id, session_id=session_id)

    async def get_agent_async(self, chat_id: int) -> str | None:
        async with self._lock:
            return self.get_agent(chat_id)

    async def set_agent_async(self, chat_id: int, agent: str) -> None:
        async with self._lock:
            self.set_agent(chat_id=chat_id, agent=agent)

    async def get_model_async(self, chat_id: int) -> ModelSelection | None:
        async with self._lock:
            return self.get_model(chat_id)

    async def set_model_async(self, chat_id: int, provider_id: str, model_id: str) -> None:
        async with self._lock:
            self.set_model(chat_id=chat_id, provider_id=provider_id, model_id=model_id)

    async def register_model_option_async(self, provider_id: str, model_id: str) -> str:
        async with self._lock:
            return self.register_model_option(provider_id=provider_id, model_id=model_id)

    async def get_model_option_async(self, option_id: str) -> ModelSelection | None:
        async with self._lock:
            return self.get_model_option(option_id)
