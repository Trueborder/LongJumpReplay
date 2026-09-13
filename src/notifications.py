from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NoticeSeverity(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    PENDING = "pending"
    QUESTION = "question"


NOTICE_SYMBOLS: dict[NoticeSeverity, str] = {
    NoticeSeverity.INFO: "ⓘ",
    NoticeSeverity.SUCCESS: "✓",
    NoticeSeverity.WARNING: "⚠",
    NoticeSeverity.ERROR: "✕",
    NoticeSeverity.PENDING: "…",
    NoticeSeverity.QUESTION: "?",
}


@dataclass(frozen=True, slots=True)
class Notice:
    message: str
    severity: NoticeSeverity = NoticeSeverity.INFO
    duration_seconds: float = 5.0
    code: str = ""

    @property
    def display_text(self) -> str:
        return f"{NOTICE_SYMBOLS[self.severity]}  {self.message}"
