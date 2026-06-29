import asyncio
import sys

from pydantic import ValidationError

from opencode_telegram.startup import run_bot


def main() -> None:
    try:
        asyncio.run(run_bot())
    except ValidationError as exc:
        print(format_startup_error(exc), file=sys.stderr)
        raise SystemExit(2) from exc


def format_startup_error(exc: ValidationError) -> str:
    fields = ", ".join(str(error["loc"][0]) for error in exc.errors())
    return f"Invalid configuration in environment or .env. Check: {fields}"
