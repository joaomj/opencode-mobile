import contextlib
import contextvars
from collections.abc import Iterator

_SESSION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")
_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


def get_session_id() -> str:
    return _SESSION_ID.get()


@contextlib.contextmanager
def session_context(session_id: str) -> Iterator[None]:
    token = _SESSION_ID.set(session_id)
    try:
        yield
    finally:
        _SESSION_ID.reset(token)
