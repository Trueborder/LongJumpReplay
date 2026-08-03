from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections.abc import Callable, Iterable

from .config import CompetitionConfig
from .models import AttemptDecision, AttemptSession


SYMBOLS = {
    AttemptDecision.NOT_DECIDED: "●",
    AttemptDecision.VALID: "✓",
    AttemptDecision.FOUL: "×",
    AttemptDecision.REVIEW: "?",
    AttemptDecision.PASSED: "–",
    AttemptDecision.MISSING: "DNS",
    AttemptDecision.WITHDRAWN: "W",
    AttemptDecision.REATTEMPT: "↻",
}


class CompetitionBoard(ttk.Frame):
    """Scrollable athlete-by-attempt matrix.

    It redraws only when roster data changes, not on every video frame. The
    Canvas approach allows per-cell colours and a strong active-cell outline,
    which ttk.Treeview cannot provide.
    """

    def __init__(
        self,
        parent,
        palette: dict[str, str],
        on_open_attempt: Callable[[int], None],
        on_select_athlete: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.palette = palette
        self.on_open_attempt = on_open_attempt
        self.on_select_athlete = on_select_athlete
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, background=palette["surface"])
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._cell_attempts: dict[tuple[int, int], int] = {}
        self._cell_boxes: list[tuple[int, int, int, int, int, int]] = []
        self._config: CompetitionConfig | None = None
        self._group = "Boys"
        self._active_athlete = 1
        self._active_attempt = 1
        self._language = "en"
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-1>", self._double_click)
        self.canvas.bind("<MouseWheel>", self._wheel)

    def apply_palette(self, palette: dict[str, str]) -> None:
        self.palette = palette
        self.canvas.configure(background=palette["surface"])
        self.redraw()

    def set_data(
        self,
        config: CompetitionConfig,
        group: str,
        attempts: Iterable[AttemptSession],
        active_athlete: int,
        active_attempt: int,
        language: str = "en",
    ) -> None:
        self._config = config
        self._group = group
        self._active_athlete = active_athlete
        self._active_attempt = active_attempt
        self._language = language if language in {"en", "cs"} else "en"
        self._attempts = list(attempts)
        self.redraw()

    def redraw(self) -> None:
        self.canvas.delete("all")
        self._cell_attempts = {}
        self._cell_boxes = []
        config = self._config
        if not config or not config.enabled:
            text = "Competition management is disabled" if self._language == "en" else "Správa soutěže je vypnutá"
            self.canvas.create_text(18, 18, text=text, anchor="nw", fill=self.palette["muted"], font=("Segoe UI", 9))
            self.canvas.configure(scrollregion=(0, 0, 500, 200))
            return
        count = config.boys_competitors if self._group == "Boys" else config.girls_competitors
        qualification_cols = config.default_attempts_per_competitor
        final_cols = config.final_attempts if config.final_round_enabled else 0
        total_cols = qualification_cols + final_cols
        row_h, athlete_w, cell_w, header_h = 34, 92, 62, 52
        width = athlete_w + total_cols * cell_w + 2
        height = header_h + max(1, count) * row_h + 2
        p = self.palette

        self.canvas.create_rectangle(0, 0, width, header_h, fill=p["surface2"], outline=p["border"])
        athlete_label = "Athlete" if self._language == "en" else "Závodník"
        attempt_label = "Attempt" if self._language == "en" else "Pokus"
        self.canvas.create_text(12, header_h / 2, text=athlete_label, anchor="w", fill=p["muted"], font=("Segoe UI Semibold", 9))
        for col in range(1, total_cols + 1):
            x0 = athlete_w + (col - 1) * cell_w
            phase = "Q" if col <= qualification_cols else "F"
            self.canvas.create_rectangle(x0, 0, x0 + cell_w, header_h, fill=p["surface2"], outline=p["border"])
            self.canvas.create_text(x0 + cell_w / 2, 18, text=f"{phase}{col if phase == 'Q' else col - qualification_cols}", fill=p["text"], font=("Segoe UI Semibold", 9))
            self.canvas.create_text(x0 + cell_w / 2, 36, text=attempt_label, fill=p["muted"], font=("Segoe UI", 7))

        by_key: dict[tuple[int, int], AttemptSession] = {}
        for attempt in getattr(self, "_attempts", []):
            if attempt.competitor_group == self._group and attempt.competitor_number > 0 and attempt.competitor_attempt_number > 0:
                existing = by_key.get((attempt.competitor_number, attempt.competitor_attempt_number))
                if existing is None or attempt.created_wall_time > existing.created_wall_time:
                    by_key[(attempt.competitor_number, attempt.competitor_attempt_number)] = attempt

        finalists = set(config.finalist_numbers_by_group.get(self._group, []))
        for athlete in range(1, count + 1):
            y0 = header_h + (athlete - 1) * row_h
            active_row = athlete == self._active_athlete
            row_fill = p["selection"] if active_row else p["surface"]
            self.canvas.create_rectangle(0, y0, athlete_w, y0 + row_h, fill=row_fill, outline=p["border"])
            self.canvas.create_text(12, y0 + row_h / 2, text=f"#{athlete:02d}", anchor="w", fill=p["text"], font=("Segoe UI Semibold", 9))
            for col in range(1, total_cols + 1):
                x0 = athlete_w + (col - 1) * cell_w
                is_final_cell = col > qualification_cols
                athlete_qualification = int(config.attempts_overrides.get(f"{self._group}:{athlete}", config.default_attempts_per_competitor))
                attempt_no = col if not is_final_cell else athlete_qualification + (col - qualification_cols)
                eligible = (col <= athlete_qualification) if not is_final_cell else athlete in finalists
                attempt = by_key.get((athlete, attempt_no))
                decision = attempt.decision if attempt else None
                fill = p["surface2"] if eligible else p["bg"]
                if decision is AttemptDecision.VALID:
                    fill = p["valid_soft"]
                elif decision is AttemptDecision.FOUL:
                    fill = p["foul_soft"]
                elif decision is AttemptDecision.REVIEW:
                    fill = p["review_soft"]
                elif decision is not None:
                    fill = p["pending_soft"]
                outline = p["accent"] if athlete == self._active_athlete and attempt_no == self._active_attempt else p["border"]
                line_width = 3 if athlete == self._active_athlete and attempt_no == self._active_attempt else 1
                self.canvas.create_rectangle(x0, y0, x0 + cell_w, y0 + row_h, fill=fill, outline=outline, width=line_width)
                text = SYMBOLS.get(decision, "") if eligible else ""
                self.canvas.create_text(x0 + cell_w / 2, y0 + row_h / 2, text=text, fill=p["text"] if eligible else p["muted"], font=("Segoe UI Semibold", 11))
                self._cell_boxes.append((x0, y0, x0 + cell_w, y0 + row_h, athlete, attempt_no))
                if attempt:
                    self._cell_attempts[(athlete, attempt_no)] = attempt.attempt_id
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _hit(self, x: int, y: int) -> tuple[int, int] | None:
        cx, cy = int(self.canvas.canvasx(x)), int(self.canvas.canvasy(y))
        for x0, y0, x1, y1, athlete, attempt_no in self._cell_boxes:
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                return athlete, attempt_no
        return None

    def _click(self, event) -> None:
        hit = self._hit(event.x, event.y)
        if not hit:
            return
        athlete, _attempt_no = hit
        if self.on_select_athlete:
            self.on_select_athlete(athlete)

    def _double_click(self, event) -> None:
        hit = self._hit(event.x, event.y)
        if not hit:
            return
        attempt_id = self._cell_attempts.get(hit)
        if attempt_id:
            self.on_open_attempt(attempt_id)

    def _wheel(self, event) -> str:
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"
