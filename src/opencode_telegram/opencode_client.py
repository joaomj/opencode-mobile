from collections.abc import AsyncIterator

import httpx
from pydantic import BaseModel, Field

from opencode_telegram.config import RuntimeConfig, Settings
from opencode_telegram.session_state import ModelSelection


class Command(BaseModel):
    name: str
    description: str = ""


class Session(BaseModel):
    id: str
    title: str | None = None


class Agent(BaseModel):
    name: str
    description: str = ""
    mode: str = "all"


class Model(BaseModel):
    id: str
    name: str = ""


class Provider(BaseModel):
    id: str
    name: str = ""
    models: dict[str, Model] = Field(default_factory=dict)


class ConfigProviders(BaseModel):
    providers: list[Provider]
    default: dict[str, str] = Field(default_factory=dict)


class TextPart(BaseModel):
    type: str = "text"
    text: str = ""


class Message(BaseModel):
    id: str | None = None
    parts: list[TextPart] = Field(default_factory=list)

    def assistant_text(self) -> str:
        return "".join(part.text for part in self.parts if part.type == "text")


class MessageListEntry(BaseModel):
    info: dict[str, object] = Field(default_factory=dict)
    parts: list[TextPart] = Field(default_factory=list)

    def assistant_text(self) -> str:
        return "".join(part.text for part in self.parts if part.type == "text")


class MessageRequest(BaseModel):
    parts: list[TextPart]
    agent: str | None = None
    model: ModelSelection | None = None


class CommandRequest(BaseModel):
    command: str
    arguments: str = ""
    agent: str | None = None
    model: str | None = None


class PermissionResponse(BaseModel):
    response: str
    remember: bool = False


class OpencodeClient:
    def __init__(self, settings: Settings, runtime: RuntimeConfig | None = None) -> None:
        self._settings = settings
        self._runtime = runtime or RuntimeConfig()
        self._client = httpx.AsyncClient(
            base_url=str(settings.opencode_base_url),
            auth=(settings.opencode_server_username, settings.opencode_server_password),
            timeout=self._runtime.opencode_request_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def list_commands(self) -> list[Command]:
        response = await self._client.get("/command")
        response.raise_for_status()
        return [Command.model_validate(item) for item in response.json()]

    async def list_sessions(self) -> list[Session]:
        response = await self._client.get("/session")
        response.raise_for_status()
        return [Session.model_validate(item) for item in response.json()]

    async def list_agents(self) -> list[Agent]:
        response = await self._client.get("/agent")
        response.raise_for_status()
        return [Agent.model_validate(item) for item in response.json()]

    async def list_config_providers(self) -> ConfigProviders:
        response = await self._client.get("/config/providers")
        response.raise_for_status()
        return ConfigProviders.model_validate(response.json())

    async def create_session(self, title: str | None = None) -> Session:
        body = {"title": title} if title is not None else None
        response = await self._client.post("/session", json=body)
        response.raise_for_status()
        return Session.model_validate(response.json())

    async def send_message(
        self,
        session_id: str,
        text: str,
        agent: str | None = None,
        model: ModelSelection | None = None,
    ) -> Message:
        request = MessageRequest(parts=[TextPart(text=text)], agent=agent, model=model)
        response = await self._client.post(
            f"/session/{session_id}/message",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        response.raise_for_status()
        return Message.model_validate(response.json())

    async def run_command(
        self,
        session_id: str,
        command: str,
        arguments: str,
        agent: str | None = None,
        model: ModelSelection | None = None,
    ) -> Message:
        model_id = f"{model.provider_id}/{model.model_id}" if model is not None else None
        request = CommandRequest(command=command, arguments=arguments, agent=agent, model=model_id)
        response = await self._client.post(
            f"/session/{session_id}/command",
            json=request.model_dump(exclude_none=True),
        )
        response.raise_for_status()
        return Message.model_validate(response.json())

    async def abort_session(self, session_id: str) -> None:
        response = await self._client.post(f"/session/{session_id}/abort")
        response.raise_for_status()

    async def respond_permission(
        self,
        session_id: str,
        permission_id: str,
        response_text: str,
    ) -> None:
        request = PermissionResponse(response=response_text)
        response = await self._client.post(
            f"/session/{session_id}/permissions/{permission_id}",
            json=request.model_dump(),
        )
        response.raise_for_status()

    async def send_prompt_async(
        self,
        session_id: str,
        text: str,
        agent: str | None = None,
        model: ModelSelection | None = None,
    ) -> None:
        request = MessageRequest(parts=[TextPart(text=text)], agent=agent, model=model)
        response = await self._client.post(
            f"/session/{session_id}/prompt_async",
            json=request.model_dump(exclude_none=True, by_alias=True),
        )
        response.raise_for_status()

    async def get_last_message(self, session_id: str) -> MessageListEntry | None:
        response = await self._client.get(f"/session/{session_id}/message?limit=1")
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        return MessageListEntry.model_validate(data[-1])

    async def events(self) -> AsyncIterator[str]:
        async with self._client.stream("GET", "/event") as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield line
