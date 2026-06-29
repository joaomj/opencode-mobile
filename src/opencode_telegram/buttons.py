from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from opencode_telegram.models import Session

CONTROL_NEW_SESSION = "c:new"
CONTROL_SESSIONS = "c:list"
CONTROL_STOP = "c:stop"


def control_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("+ New session", callback_data=CONTROL_NEW_SESSION)],
            [InlineKeyboardButton("Sessions", callback_data=CONTROL_SESSIONS)],
            [InlineKeyboardButton("Stop", callback_data=CONTROL_STOP)],
        ]
    )


def sessions_keyboard(sessions: list[Session]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    session.title or session.id,
                    callback_data=f"ses:{session.id}",
                )
            ]
            for session in sessions
        ]
    )
