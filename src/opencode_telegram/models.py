from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_none_to_empty_str(v: object) -> str:
    if v is None:
        return ""
    return str(v)


class Command(BaseModel):
    name: str
    description: str = ""
    source: str = ""
    agent: str | None = None
    model: str | None = None

    _validate_description = field_validator("description", "source", mode="before")(
        _coerce_none_to_empty_str
    )


class Session(BaseModel):
    id: str
    title: str | None = None


class TextPart(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    session_id: str = Field(default="", alias="sessionID")
    message_id: str = Field(default="", alias="messageID")
    type: str = "text"
    text: str = ""


class TextPartInput(BaseModel):
    id: str | None = None
    type: str = "text"
    text: str = ""


class MessageInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = ""
    session_id: str = Field(default="", alias="sessionID")
    role: str = ""


class Message(BaseModel):
    id: str | None = None
    role: str | None = None
    info: MessageInfo | None = None
    parts: list[TextPart] = Field(default_factory=list)

    def assistant_text(self) -> str:
        return "".join(part.text for part in self.parts if part.type == "text")


class MessageRequest(BaseModel):
    parts: list[TextPartInput]


class CommandRequest(BaseModel):
    command: str
    arguments: str = ""


class PermissionReplyRequest(BaseModel):
    reply: str
    message: str | None = None


class PermissionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    session_id: str = Field(alias="sessionID")
    permission: str
    patterns: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    always: list[str] = Field(default_factory=list)
    tool: dict[str, Any] = Field(default_factory=dict)
