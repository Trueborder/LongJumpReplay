from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
import time

from .models import BufferStats, CaptureStats


class JsonLineFormatter(logging.Formatter):
    """JSON-lines formatter for support bundles and soak tests."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "thread": record.threadName,
        }
        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(event_data)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_runtime_logging(log_path: Path) -> logging.Logger:
    """Configure one bounded application log without duplicate handlers."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("long_jump_replay")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    resolved = log_path.resolve()
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == resolved:
            return logger
    handler = RotatingFileHandler(resolved, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    return logger


def log_event(logger: logging.Logger, event: str, **values: object) -> None:
    logger.info(event, extra={"event_data": {"event": event, **values}})


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    uptime_seconds: float
    ui_average_ms: float
    ui_p95_ms: float
    ui_max_ms: float
    ui_stalls_over_100ms: int
    capture: dict[str, object]
    buffer: dict[str, object]


class RuntimeTelemetry:
    """Thread-safe, bounded in-memory UI and capture measurements."""

    def __init__(self, max_ui_samples: int = 1800) -> None:
        self._started = time.monotonic()
        self._ui_ms: deque[float] = deque(maxlen=max(60, max_ui_samples))
        self._ui_stalls = 0
        self._lock = Lock()

    def record_ui_tick(self, duration_seconds: float) -> None:
        duration_ms = max(0.0, duration_seconds * 1000.0)
        with self._lock:
            self._ui_ms.append(duration_ms)
            if duration_ms >= 100.0:
                self._ui_stalls += 1

    def snapshot(self, capture: CaptureStats, buffer: BufferStats) -> RuntimeSnapshot:
        with self._lock:
            samples = sorted(self._ui_ms)
            stalls = self._ui_stalls
        average = sum(samples) / len(samples) if samples else 0.0
        p95_index = max(0, min(len(samples) - 1, int(len(samples) * .95))) if samples else 0
        return RuntimeSnapshot(
            uptime_seconds=max(0.0, time.monotonic() - self._started),
            ui_average_ms=average,
            ui_p95_ms=samples[p95_index] if samples else 0.0,
            ui_max_ms=samples[-1] if samples else 0.0,
            ui_stalls_over_100ms=stalls,
            capture=asdict(capture),
            buffer=asdict(buffer),
        )
