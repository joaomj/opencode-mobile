from pydantic import BaseModel

from opencode_telegram.models import Command


class ParsedCommand(BaseModel):
    name: str
    arguments: str = ""


def resolve_slash_command(text: str, commands: list[Command]) -> ParsedCommand | None:
    if not text.startswith("/"):
        return None

    command_text = text[1:].strip()
    if not command_text:
        return None

    name, separator, arguments = command_text.partition(" ")
    known_names = {command.name for command in commands}
    if name not in known_names:
        return None

    return ParsedCommand(name=name, arguments=arguments.strip() if separator else "")
