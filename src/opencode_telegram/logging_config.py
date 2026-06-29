import logging
from datetime import date, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from opencode_telegram._logging_context import _CORRELATION_ID
from opencode_telegram.config import RuntimeConfig

_MASK_TEXT = "***"
_LOG_DATE_FORMAT = "%Y-%m-%d"
_LOG_FILE_STEM = "opencode-telegram"
_LOG_FILE_SUFFIX = ".log"


class CorrelationFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "correlation_id"):
            record.correlation_id = _CORRELATION_ID.get()
        return super().format(record)


class TokenMaskingFormatter(CorrelationFormatter):
    def __init__(self, token: str, fmt: str | None = None) -> None:
        super().__init__(fmt)
        self._token = token

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)
        return result.replace(self._token, _MASK_TEXT)


class DailySizeRotatingFileHandler(RotatingFileHandler):
    def __init__(self, filename: str, runtime: RuntimeConfig) -> None:
        self._base_path = Path(filename)
        self._current_date = date.today().strftime(_LOG_DATE_FORMAT)
        super().__init__(
            filename=str(_build_log_path(runtime, self._current_date)),
            maxBytes=runtime.log_max_bytes,
            backupCount=runtime.log_backup_count,
        )
        self._retention_days = runtime.log_retention_days

    def shouldRollover(self, record: logging.LogRecord) -> int:
        current_date = date.today().strftime(_LOG_DATE_FORMAT)
        if current_date != self._current_date:
            return True
        return super().shouldRollover(record)

    def doRollover(self) -> None:
        current_date = date.today().strftime(_LOG_DATE_FORMAT)
        if current_date != self._current_date:
            if self.stream:
                self.stream.close()
                self.stream = None
            self._current_date = current_date
            self.baseFilename = str(_build_log_path_from_base(self._base_path, current_date))
        super().doRollover()
        self._cleanup_old_logs()

    def _cleanup_old_logs(self) -> None:
        cutoff = date.today() - timedelta(days=self._retention_days - 1)
        for path in self._base_path.parent.glob(f"{_LOG_FILE_STEM}-*{_LOG_FILE_SUFFIX}*"):
            log_date = _date_from_log_path(path)
            if log_date is not None and log_date < cutoff:
                path.unlink(missing_ok=True)


def _build_log_path(runtime: RuntimeConfig, date_text: str | None = None) -> Path:
    return _build_log_path_from_base(
        base_path=Path(runtime.log_file),
        date_text=date_text or date.today().strftime(_LOG_DATE_FORMAT),
    )


def _build_log_path_from_base(base_path: Path, date_text: str) -> Path:
    return base_path.with_name(f"{_LOG_FILE_STEM}-{date_text}{_LOG_FILE_SUFFIX}")


def _date_from_log_path(path: Path) -> date | None:
    name = path.name
    prefix = f"{_LOG_FILE_STEM}-"
    if not name.startswith(prefix):
        return None
    date_text = name.removeprefix(prefix)[: len(_LOG_DATE_FORMAT)]
    try:
        return datetime.strptime(date_text, _LOG_DATE_FORMAT).date()
    except ValueError:
        return None


def configure_logging(runtime: RuntimeConfig, bot_token: str) -> None:
    log_path = _build_log_path(runtime)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, runtime.log_level))

    fmt = "%(asctime)s %(levelname)s %(name)s cid=%(correlation_id)s %(message)s"
    masked_formatter = TokenMaskingFormatter(token=bot_token, fmt=fmt)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(masked_formatter)
    root_logger.addHandler(stream_handler)

    file_handler = DailySizeRotatingFileHandler(filename=runtime.log_file, runtime=runtime)
    file_handler.setFormatter(masked_formatter)
    root_logger.addHandler(file_handler)

    if runtime.telegram_http_logs:
        logging.getLogger("httpx").setLevel(logging.DEBUG)
    else:
        logging.getLogger("httpx").setLevel(logging.WARNING)

    LOGGER = logging.getLogger(__name__)
    LOGGER.info("logging to file: %s", log_path)
