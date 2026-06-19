from opencode_telegram.native_commands import is_native_selector_command


def test_native_selector_commands_are_recognized() -> None:
    assert is_native_selector_command("/agents")
    assert is_native_selector_command("/models")


def test_native_selector_command_arguments_do_not_match() -> None:
    assert not is_native_selector_command("/agents extra")
