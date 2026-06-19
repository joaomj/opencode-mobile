from opencode_telegram.commands import ParsedCommand, resolve_slash_command
from opencode_telegram.opencode_client import Command


def test_real_command_is_resolved_with_arguments() -> None:
    commands = [Command(name="plan", description="Create a plan")]

    result = resolve_slash_command("/plan ship it", commands)

    assert result == ParsedCommand(name="plan", arguments="ship it")


def test_unknown_command_is_rejected() -> None:
    commands = [Command(name="plan", description="Create a plan")]

    result = resolve_slash_command("/missing args", commands)

    assert result is None


def test_plain_text_is_not_a_slash_command() -> None:
    commands = [Command(name="plan", description="Create a plan")]

    result = resolve_slash_command("please plan", commands)

    assert result is None
