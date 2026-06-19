from opencode_telegram.config import RuntimeConfig


def truncate_telegram(text: str, runtime: RuntimeConfig | None = None) -> str:
    config = runtime or RuntimeConfig()
    if len(text) <= config.telegram_message_limit:
        return text
    suffix = "..."
    return text[: config.telegram_message_limit - len(suffix)] + suffix


def split_long_message(text: str, runtime: RuntimeConfig | None = None) -> list[str]:
    config = runtime or RuntimeConfig()
    limit = config.telegram_message_limit
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + limit
        chunks.append(text[start:end])
        start = end
    return chunks
