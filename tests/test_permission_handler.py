import pytest

from opencode_telegram.permission_handler import (
    build_permission_keyboard,
    parse_permission_callback,
)

_EXPECTED_BUTTON_COUNT = 4


def test_build_permission_keyboard_has_four_buttons() -> None:
    keyboard = build_permission_keyboard(short_id="abc123")

    buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    assert len(buttons) == _EXPECTED_BUTTON_COUNT
    assert buttons[0].callback_data == "pa:abc123"
    assert buttons[0].text == "Allow"
    assert buttons[1].callback_data == "pd:abc123"
    assert buttons[1].text == "Deny"
    assert buttons[2].callback_data == "par:abc123"
    assert buttons[2].text == "Allow + remember"
    assert buttons[3].callback_data == "pdr:abc123"
    assert buttons[3].text == "Deny + remember"


@pytest.mark.parametrize(
    ("callback_data", "expected_response", "expected_remember"),
    [
        ("pa:abc123", "allow", False),
        ("par:abc123", "allow", True),
        ("pd:abc123", "deny", False),
        ("pdr:abc123", "deny", True),
    ],
)
def test_parse_permission_callback(
    callback_data: str, expected_response: str, expected_remember: bool
) -> None:
    result = parse_permission_callback(callback_data)

    assert result is not None
    assert result.response == expected_response
    assert result.remember is expected_remember
    assert result.short_id == "abc123"


def test_parse_permission_callback_returns_none_for_other_data() -> None:
    assert parse_permission_callback("ses:abc123") is None
    assert parse_permission_callback("unknown") is None
