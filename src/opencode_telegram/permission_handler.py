from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@dataclass(frozen=True)
class PermissionCallback:
    response: str
    remember: bool
    short_id: str


_CALLBACK_PREFIXES = [
    ("pa:", "allow", False),
    ("par:", "allow", True),
    ("pd:", "deny", False),
    ("pdr:", "deny", True),
]


def build_permission_keyboard(short_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Allow", callback_data=f"pa:{short_id}"),
                InlineKeyboardButton("Deny", callback_data=f"pd:{short_id}"),
            ],
            [
                InlineKeyboardButton(
                    "Allow + remember", callback_data=f"par:{short_id}"
                ),
                InlineKeyboardButton(
                    "Deny + remember", callback_data=f"pdr:{short_id}"
                ),
            ],
        ]
    )


def parse_permission_callback(callback_data: str) -> PermissionCallback | None:
    for prefix, response, remember in _CALLBACK_PREFIXES:
        if callback_data.startswith(prefix):
            short_id = callback_data.removeprefix(prefix)
            return PermissionCallback(
                response=response,
                remember=remember,
                short_id=short_id,
            )
    return None
