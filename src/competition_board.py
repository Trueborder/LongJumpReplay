from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk
from collections.abc import Callable, Iterable

from .config import CompetitionConfig
from .i18n import tr
from .language_catalog import normalize_language
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
        on_select_cell: Callable[[int, int], None] | None = None,
        on_mark_attempt: Callable[[int, AttemptDecision], None] | None = None,
        on_mark_empty_cell: Callable[[int, int, AttemptDecision], None] | None = None,
        on_delete_attempt: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.palette = palette
        self.on_open_attempt = on_open_attempt
        self.on_select_cell = on_select_cell
        self.on_mark_attempt = on_mark_attempt
        self.on_mark_empty_cell = on_mark_empty_cell
        self.on_delete_attempt = on_delete_attempt
        self.canvas = tk.Canvas(self, highlightthickness=1, highlightbackground=palette["border"], bd=0, background=palette["surface"], takefocus=True)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self._cell_attempts: dict[tuple[int, int], int] = {}
        self._editable_cells: set[tuple[int, int]] = set()
        self._cell_boxes: list[tuple[int, int, int, int, int, int]] = []
        self._cell_items: dict[tuple[int, int], tuple[int, str]] = {}
        self._cell_positions: dict[tuple[int, int], tuple[int, int]] = {}
        self._cell_grid: list[list[tuple[int, int]]] = []
        self._focused_cell: tuple[int, int] | None = None
        self._focused_group = ""
        self._pulse_started = 0.0
        self._pulse_job: str | None = None
        self._config: CompetitionConfig | None = None
        self._group = "Boys"
        self._active_athlete = 1
        self._active_attempt = 1
        self._language = "en"
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Button-3>", self._right_click)
        self.canvas.bind("<Up>", lambda _event: self.move_focus(0, -1))
        self.canvas.bind("<Down>", lambda _event: self.move_focus(0, 1))
        self.canvas.bind("<Return>", self.activate_focused)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._horizontal_wheel)
        self.canvas.bind("<Button-4>", lambda _event: self._scroll_units(-1, vertical=True))
        self.canvas.bind("<Button-5>", lambda _event: self._scroll_units(1, vertical=True))
        self.canvas.bind("<Shift-Button-4>", lambda _event: self._scroll_units(-1, vertical=False))
        self.canvas.bind("<Shift-Button-5>", lambda _event: self._scroll_units(1, vertical=False))
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Shift-MouseWheel>", self._horizontal_wheel)
        self.bind("<Button-4>", lambda _e: self._scroll_units(-1, vertical=True))
        self.bind("<Button-5>", lambda _e: self._scroll_units(1, vertical=True))
        self.bind("<Shift-Button-4>", lambda _e: self._scroll_units(-1, vertical=False))
        self.bind("<Shift-Button-5>", lambda _e: self._scroll_units(1, vertical=False))
        self.context_menu = tk.Menu(self.canvas, tearoff=False)
        self._context_attempt_id: int | None = None
        self._context_cell: tuple[int, int] | None = None
        self._delete_menu_index = 0
        self._rebuild_context_menu()

    def apply_palette(self, palette: dict[str, str]) -> None:
        self.palette = palette
        self.canvas.configure(background=palette["surface"], highlightbackground=palette["border"])
        self._style_context_menu()
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
        if group != self._group:
            self._focused_cell = None
            self._focused_group = ""
        self._config = config
        self._group = group
        self._active_athlete = active_athlete
        self._active_attempt = active_attempt
        self._language = normalize_language(language)
        self._attempts = list(attempts)
        self._rebuild_context_menu()
        self.redraw()

    def redraw(self) -> None:
        self.canvas.delete("all")
        self._cell_attempts = {}
        self._editable_cells = set()
        self._cell_boxes = []
        self._cell_items = {}
        self._cell_positions = {}
        self._cell_grid = []
        config = self._config
        if not config or not config.enabled:
            text = tr(self._language, "competition.roster_disabled")
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
        athlete_label = tr(self._language, "table.athlete")
        attempt_label = tr(self._language, "table.attempt")
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
            grid_row: list[tuple[int, int]] = []
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
                cell = (athlete, attempt_no)
                focused = self._focused_group == self._group and self._focused_cell == cell
                active = self._focused_cell is None and athlete == self._active_athlete and attempt_no == self._active_attempt
                outline = p["accent_hover"] if focused else p["accent"] if active else p["border"]
                line_width = 3 if focused or active else 1
                rectangle = self.canvas.create_rectangle(x0, y0, x0 + cell_w, y0 + row_h, fill=fill, outline=outline, width=line_width)
                text = SYMBOLS.get(decision, "") if eligible else ""
                self.canvas.create_text(x0 + cell_w / 2, y0 + row_h / 2, text=text, fill=p["text"] if eligible else p["muted"], font=("Segoe UI Semibold", 11))
                self._cell_boxes.append((x0, y0, x0 + cell_w, y0 + row_h, athlete, attempt_no))
                self._cell_items[cell] = (rectangle, fill)
                self._cell_positions[cell] = (athlete - 1, col - 1)
                grid_row.append(cell)
                if eligible:
                    self._editable_cells.add(cell)
                if attempt:
                    self._cell_attempts[(athlete, attempt_no)] = attempt.attempt_id
            self._cell_grid.append(grid_row)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self._schedule_focus_pulse()

    @staticmethod
    def _blend(first: str, second: str, amount: float) -> str:
        amount = max(0.0, min(1.0, amount))
        left = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
        right = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
        values = tuple(round(a + (b - a) * amount) for a, b in zip(left, right))
        return "#" + "".join(f"{value:02x}" for value in values)

    def focus_cell(self, cell: tuple[int, int] | None) -> None:
        self._focused_cell = cell
        self._focused_group = self._group if cell is not None else ""
        self._pulse_started = time.monotonic()
        self.redraw()
        if cell is not None:
            self._ensure_cell_visible(cell)

    def clear_focus(self) -> None:
        if self._focused_cell is not None:
            self.focus_cell(None)

    def _schedule_focus_pulse(self) -> None:
        if self._focused_cell is None or self._focused_group != self._group:
            if self._pulse_job is not None:
                try: self.after_cancel(self._pulse_job)
                except tk.TclError: pass
                self._pulse_job = None
            return
        if self._pulse_job is None:
            self._pulse_job = self.after(50, self._animate_focus)

    def _animate_focus(self) -> None:
        self._pulse_job = None
        if self._focused_cell is None or self._focused_group != self._group:
            return
        item = self._cell_items.get(self._focused_cell)
        if item is None:
            self._focused_cell = None
            self._focused_group = ""
            return
        rectangle, base_fill = item
        wave = (math.sin((time.monotonic() - self._pulse_started) * math.tau / 1.4) + 1.0) / 2.0
        pulse_fill = self._blend(base_fill, self.palette["accent_hover"], 0.12 + wave * 0.28)
        try:
            self.canvas.itemconfigure(rectangle, fill=pulse_fill, outline=self.palette["accent_hover"], width=3)
        except tk.TclError:
            return
        self._schedule_focus_pulse()

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
        self.canvas.focus_set()
        self.focus_cell(hit)
        self._activate_cell(hit)

    def _activate_cell(self, hit: tuple[int, int]) -> None:
        attempt_id = self._cell_attempts.get(hit)
        if attempt_id is not None:
            self.on_open_attempt(attempt_id)
            return
        if self.on_select_cell:
            self.on_select_cell(*hit)

    def activate_focused(self, _event=None) -> str:
        if self._focused_cell is not None:
            self._activate_cell(self._focused_cell)
        return "break"

    def move_focus(self, dx: int, dy: int) -> str:
        if not self._cell_grid:
            return "break"
        current = self._focused_cell
        if current not in self._cell_positions:
            active = (self._active_athlete, self._active_attempt)
            current = active if active in self._cell_positions else self._cell_grid[0][0]
        row, column = self._cell_positions[current]
        row = max(0, min(len(self._cell_grid) - 1, row + dy))
        column = max(0, min(len(self._cell_grid[row]) - 1, column + dx))
        self.focus_cell(self._cell_grid[row][column])
        return "break"

    def _ensure_cell_visible(self, cell: tuple[int, int]) -> None:
        box = next((entry[:4] for entry in self._cell_boxes if entry[4:] == cell), None)
        if box is None:
            return
        x0, y0, x1, y1 = box
        try:
            sx0, sy0, sx1, sy1 = (float(value) for value in str(self.canvas.cget("scrollregion")).split())
        except (TypeError, ValueError):
            return
        left, top = self.canvas.canvasx(0), self.canvas.canvasy(0)
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        if x0 < left: self.canvas.xview_moveto(max(0.0, (x0 - 8 - sx0) / max(1.0, sx1 - sx0)))
        elif x1 > left + width: self.canvas.xview_moveto(max(0.0, (x1 + 8 - width - sx0) / max(1.0, sx1 - sx0)))
        if y0 < top: self.canvas.yview_moveto(max(0.0, (y0 - 8 - sy0) / max(1.0, sy1 - sy0)))
        elif y1 > top + height: self.canvas.yview_moveto(max(0.0, (y1 + 8 - height - sy0) / max(1.0, sy1 - sy0)))

    def _right_click(self, event) -> str:
        hit = self._hit(event.x, event.y)
        if hit is None:
            return "break"
        self.canvas.focus_set(); self.focus_cell(hit)
        if not self._prepare_context_cell(hit):
            return "break"
        try: self.context_menu.tk_popup(event.x_root, event.y_root)
        finally: self.context_menu.grab_release()
        return "break"

    def _prepare_context_cell(self, hit: tuple[int, int]) -> bool:
        attempt_id = self._cell_attempts.get(hit)
        if attempt_id is None and hit not in self._editable_cells:
            return False
        self._context_attempt_id = attempt_id
        self._context_cell = hit
        self.context_menu.entryconfigure(self._delete_menu_index, state="normal" if attempt_id is not None else "disabled")
        return True

    def _rebuild_context_menu(self) -> None:
        self.context_menu.delete(0, "end")
        for decision, key in (
            (AttemptDecision.NOT_DECIDED, "status.not_decided"), (AttemptDecision.VALID, "status.valid"),
            (AttemptDecision.FOUL, "status.foul"), (AttemptDecision.REVIEW, "status.review"),
            (AttemptDecision.PASSED, "status.passed"), (AttemptDecision.MISSING, "status.missing"),
            (AttemptDecision.WITHDRAWN, "status.withdrawn"),
        ):
            self.context_menu.add_command(label=tr(self._language, key), command=lambda value=decision: self._context_mark(value))
        self.context_menu.add_separator()
        self.context_menu.add_command(label=tr(self._language, "board.delete_attempt"), command=self._context_delete)
        self._delete_menu_index = int(self.context_menu.index("end"))
        self._style_context_menu()

    def _style_context_menu(self) -> None:
        p = self.palette
        try: self.context_menu.configure(background=p["surface"], foreground=p["text"], activebackground=p["selection"], activeforeground=p["text"], disabledforeground=p["muted"], font=("Segoe UI", 10), relief="solid", borderwidth=1, activeborderwidth=0)
        except tk.TclError: pass

    def _context_mark(self, decision: AttemptDecision) -> None:
        if self._context_attempt_id is not None and self.on_mark_attempt:
            self.on_mark_attempt(self._context_attempt_id, decision)
        elif self._context_cell is not None and self.on_mark_empty_cell:
            self.on_mark_empty_cell(*self._context_cell, decision)

    def _context_delete(self) -> None:
        if self._context_attempt_id is not None and self.on_delete_attempt:
            self.on_delete_attempt(self._context_attempt_id)

    def _wheel(self, event) -> str:
        delta = getattr(event, "delta", 0)
        amount = max(1, abs(delta) // 120) if delta else 1
        self._scroll_units(-amount if delta >= 0 else amount, vertical=True)
        return "break"

    def _horizontal_wheel(self, event) -> str:
        delta = getattr(event, "delta", 0)
        amount = max(1, abs(delta) // 120) if delta else 1
        self._scroll_units(-amount if delta >= 0 else amount, vertical=False)
        return "break"

    def _scroll_units(self, amount: int, vertical: bool = True) -> str:
        (self.canvas.yview_scroll if vertical else self.canvas.xview_scroll)(amount, "units")
        return "break"

    def destroy(self) -> None:
        if self._pulse_job is not None:
            try: self.after_cancel(self._pulse_job)
            except tk.TclError: pass
            self._pulse_job = None
        super().destroy()
