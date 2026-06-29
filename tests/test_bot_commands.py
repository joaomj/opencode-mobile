from opencode_telegram.bot import TELEGRAM_COMMAND_DESCRIPTION_LIMIT, build_telegram_commands
from opencode_telegram.native_commands import HAMBUGER_DESCRIPTIONS
from opencode_telegram.opencode_client import Command


def test_build_telegram_commands_truncates_long_description() -> None:
    custom = [Command(name="plan", description="x" * 300)]

    result = build_telegram_commands(custom)

    native_count = len(HAMBUGER_DESCRIPTIONS)
    assert len(result) == native_count + 1
    plan = next(c for c in result if c.command == "plan")
    assert len(plan.description) == TELEGRAM_COMMAND_DESCRIPTION_LIMIT
    assert plan.description.endswith("...")


def test_build_telegram_commands_skips_invalid_telegram_names() -> None:
    custom = [
        Command(name="valid_name", description="Valid"),
        Command(name="invalid-name", description="Invalid"),
        Command(name="UPPER", description="Invalid"),
    ]

    result = build_telegram_commands(custom)

    names = [c.command for c in result]
    assert "valid_name" in names
    assert "invalid-name" not in names
    assert "UPPER" not in names


def test_build_telegram_commands_excludes_skill_commands() -> None:
    custom = [
        Command(name="my_command", description="Made by me", source="command"),
        Command(name="skill_command", description="From a skill", source="skill"),
    ]

    result = build_telegram_commands(custom)

    names = [c.command for c in result]
    assert "my_command" in names
    assert "skill_command" not in names
