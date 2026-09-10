from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import time
from collections.abc import Callable


class AthleteTimerState(Enum):
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class AthleteTimerSnapshot:
    state: AthleteTimerState
    remaining_seconds: int
    # Tenths are kept separately so existing competition logic can continue to
    # use whole-second thresholds while the operator gets a precise display.
    remaining_tenths: int


class AthleteTimerController:
    """Operator-controlled countdown based on a monotonic clock."""

    def __init__(self, duration_seconds: int = 60, clock_ns: Callable[[], int] = time.monotonic_ns) -> None:
        self._validate_duration(duration_seconds)
        self.duration_seconds = int(duration_seconds)
        self._clock_ns = clock_ns
        self.state = AthleteTimerState.READY
        self._started_ns = 0
        self._stopped_seconds = self.duration_seconds

    @staticmethod
    def _validate_duration(duration_seconds: int) -> None:
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or not 1 <= duration_seconds <= 600:
            raise ValueError("Athlete timer duration must be an integer between 1 and 600 seconds")

    def snapshot(self) -> AthleteTimerSnapshot:
        if self.state is AthleteTimerState.RUNNING:
            remaining_ns = self.duration_seconds * 1_000_000_000 - max(0, self._clock_ns() - self._started_ns)
            if remaining_ns <= 0:
                self.state = AthleteTimerState.EXPIRED
                self._stopped_seconds = 0
            else:
                remaining_seconds = int(math.ceil(remaining_ns / 1_000_000_000))
                remaining_tenths = int(math.ceil(remaining_ns / 100_000_000))
                return AthleteTimerSnapshot(self.state, remaining_seconds, remaining_tenths)
        if self.state is AthleteTimerState.READY:
            remaining = self.duration_seconds
        elif self.state is AthleteTimerState.STOPPED:
            remaining = self._stopped_seconds
        else:
            remaining = 0
        return AthleteTimerSnapshot(self.state, remaining, max(0, int(remaining) * 10))

    def start(self) -> AthleteTimerSnapshot:
        self._started_ns = self._clock_ns()
        self._stopped_seconds = self.duration_seconds
        self.state = AthleteTimerState.RUNNING
        return self.snapshot()

    def stop(self) -> AthleteTimerSnapshot:
        current = self.snapshot()
        if current.state is AthleteTimerState.RUNNING:
            self._stopped_seconds = current.remaining_seconds
            self.state = AthleteTimerState.STOPPED
        return self.snapshot()

    def reset(self) -> AthleteTimerSnapshot:
        self.state = AthleteTimerState.READY
        self._started_ns = 0
        self._stopped_seconds = self.duration_seconds
        return self.snapshot()

    def set_duration(self, duration_seconds: int) -> AthleteTimerSnapshot:
        self._validate_duration(duration_seconds)
        self.duration_seconds = int(duration_seconds)
        return self.reset()


def format_countdown(seconds: int) -> str:
    minutes, seconds = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{seconds:02d}"


def format_countdown_tenths(total_tenths: int) -> str:
    """Format a countdown as MM:SS.t without changing the legacy formatter."""
    total_tenths = max(0, int(total_tenths))
    minutes, remainder = divmod(total_tenths, 600)
    seconds, tenth = divmod(remainder, 10)
    return f"{minutes:02d}:{seconds:02d}.{tenth}"
