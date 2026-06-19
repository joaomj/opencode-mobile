from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from opencode_telegram.opencode_client import Session

CONTROL_NEW_SESSION = "c:new"
CONTROL_SESSIONS = "c:list"
CONTROL_STOP = "c:stop"
ITEMS_PER_PAGE = 8
COLUMNS = 2
_BUTTON_LABEL_MAX = 35


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


def provider_list_keyboard(providers: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(label, callback_data=f"sp:{provider_id}")]
        for provider_id, label in providers
    ]
    rows.append([InlineKeyboardButton("Cancel", callback_data="pg:cancel")])
    return InlineKeyboardMarkup(rows)


def paginated_model_keyboard(
    items: list[tuple[str, str]],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = items[start:end]

    for i in range(0, len(page_items), COLUMNS):
        row = []
        for option_id, label in page_items[i : i + COLUMNS]:
            truncated = label[:_BUTTON_LABEL_MAX] if len(label) > _BUTTON_LABEL_MAX else label
            row.append(InlineKeyboardButton(truncated, callback_data=f"sm:{option_id}"))
        rows.append(row)

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Back", callback_data=f"pg:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="pg:cancel"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ▶", callback_data=f"pg:{page + 1}"))
    rows.append(nav_row)

    return InlineKeyboardMarkup(rows)


def paginated_agent_keyboard(
    agent_names: list[str],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    start = page * ITEMS_PER_PAGE
    end = start + ITEMS_PER_PAGE
    page_items = agent_names[start:end]

    for i in range(0, len(page_items), COLUMNS):
        row = [
            InlineKeyboardButton(name, callback_data=f"sa:{name}")
            for name in page_items[i : i + COLUMNS]
        ]
        rows.append(row)

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Back", callback_data=f"ag:{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="pg:cancel"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ▶", callback_data=f"ag:{page + 1}"))
    rows.append(nav_row)

    return InlineKeyboardMarkup(rows)
