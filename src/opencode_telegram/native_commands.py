from enum import StrEnum


class NativeCommand(StrEnum):
    CONNECT = "connect"
    AGENTS = "agents"
    CLEAR = "clear"
    COMPACT = "compact"
    CONTINUE = "continue"
    DETAILS = "details"
    EDITOR = "editor"
    EXIT = "exit"
    EXPORT = "export"
    HELP = "help"
    INIT = "init"
    MODELS = "models"
    NEW = "new"
    Q = "q"
    QUIT = "quit"
    REDO = "redo"
    RESUME = "resume"
    SESSIONS = "sessions"
    SHARE = "share"
    SUMMARIZE = "summarize"
    THEMES = "themes"
    THINKING = "thinking"
    UNDO = "undo"
    UNSHARE = "unshare"


NATIVE_COMMAND_NAMES = {command.value for command in NativeCommand}
SELECTOR_COMMANDS = {NativeCommand.AGENTS.value, NativeCommand.MODELS.value}
SESSION_LIST_COMMANDS = {
    NativeCommand.SESSIONS.value,
    NativeCommand.RESUME.value,
    NativeCommand.CONTINUE.value,
}
NEW_SESSION_COMMANDS = {NativeCommand.NEW.value, NativeCommand.CLEAR.value}
COMPACT_COMMANDS = {NativeCommand.COMPACT.value, NativeCommand.SUMMARIZE.value}
EXIT_COMMANDS = {NativeCommand.EXIT.value, NativeCommand.QUIT.value, NativeCommand.Q.value}
UNSUPPORTED_TUI_COMMANDS = {
    NativeCommand.CONNECT.value,
    NativeCommand.DETAILS.value,
    NativeCommand.EDITOR.value,
    NativeCommand.EXPORT.value,
    NativeCommand.THEMES.value,
    NativeCommand.THINKING.value,
}

# Commands that appear in the Telegram hamburger menu with descriptions.
# Only commands that do something useful in Telegram are included.
HAMBUGER_DESCRIPTIONS: dict[str, str] = {
    "new": "Start a new session",
    "sessions": "List and switch between sessions",
    "agents": "Select an agent",
    "models": "Select a model",
    "compact": "Compact the current session",
    "help": "Show available commands",
    "init": "Guided setup for AGENTS.md",
    "share": "Share current session",
    "undo": "Undo last message",
    "redo": "Redo a previously undone message",
    "unshare": "Unshare current session",
}


def parse_native_command(text: str) -> str | None:
    if not text.startswith("/"):
        return None
    command_text = text[1:].strip()
    if not command_text or " " in command_text:
        return None
    if command_text not in NATIVE_COMMAND_NAMES:
        return None
    return command_text


def is_native_selector_command(text: str) -> bool:
    command = parse_native_command(text)
    return command in SELECTOR_COMMANDS
