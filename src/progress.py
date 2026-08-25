"""Shared, truthful progress state and Tk presentation helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import tkinter as tk
from tkinter import ttk
from typing import Callable


class ProgressState(str, Enum):
    DETERMINATE = "determinate"
    INDETERMINATE = "indeterminate"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    label: str
    completed_units: int = 0
    total_units: int | None = None
    detail: str = ""
    state: ProgressState = ProgressState.DETERMINATE

    @property
    def fraction(self) -> float | None:
        if self.total_units is None or self.total_units <= 0:
            return None
        return min(1.0, max(0.0, self.completed_units / self.total_units))


@dataclass(frozen=True, slots=True)
class StartupProgressEvent:
    phase_id: str
    operation_label: str
    completed_units: int
    total_units: int
    overall_weight: float
    detail: str = ""
    state: ProgressState = ProgressState.DETERMINATE


class ProgressController:
    """Keep a progress stream monotonic and prevent premature completion."""

    def __init__(self, label: str = "") -> None:
        self._snapshot = ProgressSnapshot(label)

    @property
    def snapshot(self) -> ProgressSnapshot:
        return self._snapshot

    def update(
        self,
        *,
        label: str | None = None,
        completed_units: int | None = None,
        total_units: int | None = None,
        detail: str | None = None,
        state: ProgressState | None = None,
    ) -> ProgressSnapshot:
        old = self._snapshot
        next_total = old.total_units if total_units is None else max(0, int(total_units))
        next_completed = old.completed_units if completed_units is None else max(0, int(completed_units))
        if next_total:
            next_completed = min(next_completed, next_total)
        if old.total_units == next_total:
            next_completed = max(old.completed_units, next_completed)
        next_state = state or old.state
        if next_state is ProgressState.COMPLETED and next_total:
            next_completed = next_total
        elif next_state is not ProgressState.COMPLETED and next_total and next_completed >= next_total:
            next_completed = max(0, next_total - 1)
        self._snapshot = replace(
            old,
            label=old.label if label is None else label,
            completed_units=next_completed,
            total_units=next_total,
            detail=old.detail if detail is None else detail,
            state=next_state,
        )
        return self._snapshot


class ProgressView(ttk.Frame):
    """One labelled horizontal bar with optional details beneath it."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        style_prefix: str = "",
        show_details_toggle: bool = False,
        details_expanded: bool = False,
        details_label: str = "Details",
        hide_details_label: str = "Hide details",
        on_details_changed: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = ProgressController()
        self._on_details_changed = on_details_changed
        self._details_label = details_label
        self._hide_details_label = hide_details_label
        self._expanded = details_expanded
        self.label = ttk.Label(self, text="")
        self.label.pack(anchor="w")
        bar_style = f"{style_prefix}.Horizontal.TProgressbar" if style_prefix else "Horizontal.TProgressbar"
        self.bar = ttk.Progressbar(self, mode="determinate", maximum=100, style=bar_style)
        self.bar.pack(fill="x", pady=(5, 0))
        self.detail = ttk.Label(self, text="", style="Muted.TLabel", justify="left", wraplength=520)
        self.detail.pack(anchor="w", pady=(5, 0))
        self.toggle: ttk.Button | None = None
        self.history = tk.Text(self, height=5, wrap="word", state="disabled", takefocus=False)
        if show_details_toggle:
            self.toggle = ttk.Button(self, command=self._toggle)
            self.toggle.pack(anchor="w", pady=(6, 0))
            self._sync_details_visibility()

    @property
    def details_expanded(self) -> bool:
        return self._expanded

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._sync_details_visibility()
        if self._on_details_changed:
            self._on_details_changed(self._expanded)

    def _sync_details_visibility(self) -> None:
        if self.toggle is None:
            return
        self.toggle.configure(text=self._hide_details_label if self._expanded else self._details_label)
        if self._expanded:
            self.history.pack(fill="x", pady=(6, 0), before=self.toggle)
        else:
            self.history.pack_forget()

    def append_history(self, text: str) -> None:
        if not text:
            return
        self.history.configure(state="normal")
        self.history.insert("end", text.rstrip() + "\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    def render(self, snapshot: ProgressSnapshot) -> None:
        self._controller.update(
            label=snapshot.label,
            completed_units=snapshot.completed_units,
            total_units=snapshot.total_units,
            detail=snapshot.detail,
            state=snapshot.state,
        )
        current = self._controller.snapshot
        self.label.configure(text=current.label)
        self.detail.configure(text=current.detail)
        if current.state is ProgressState.INDETERMINATE:
            if str(self.bar.cget("mode")) != "indeterminate":
                self.bar.stop()
                self.bar.configure(mode="indeterminate")
            self.bar.start(12)
        else:
            self.bar.stop()
            self.bar.configure(mode="determinate", maximum=max(1, current.total_units or 100))
            self.bar.configure(value=current.completed_units)

