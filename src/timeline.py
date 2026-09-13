from __future__ import annotations

import math
import time
import tkinter as tk
from collections.abc import Callable
from datetime import datetime

from .models import TimelineModel
from .i18n import tr
from .language_catalog import normalize_language
from .theme import bind_resize_only


NICE_STEPS = [1 / 240, 1 / 120, 1 / 60, 1 / 30, .05, .1, .2, .5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800]


def choose_tick_step(duration_seconds: float, width: int, min_pixels: int = 84) -> float:
    target = max(1e-9, duration_seconds * min_pixels / max(1, width))
    return next((step for step in NICE_STEPS if step >= target), NICE_STEPS[-1])


def format_relative(seconds: float, detailed: bool = False) -> str:
    sign = "−" if seconds < 0 else "+"
    value = abs(seconds)
    if detailed or value < 10:
        return f"{sign}{value:0.3f}s"
    minutes, sec = divmod(value, 60)
    return f"{sign}{int(minutes):02d}:{sec:04.1f}"


def format_wall_time_ns(wall_time_ns: int) -> str:
    if not wall_time_ns:
        return "--:--:--.---"
    return datetime.fromtimestamp(wall_time_ns / 1_000_000_000).astimezone().strftime("%H:%M:%S.%f")[:-3]


def format_timeline_span(seconds: float) -> str:
    if seconds >= 3600:
        return f"{seconds / 3600:.1f} h view"
    if seconds >= 60:
        return f"{seconds / 60:.1f} min view"
    return f"{seconds:.1f} s view"


def centered_window(playhead_ns: int, duration_seconds: float) -> tuple[int, int]:
    half = max(1, int(duration_seconds * 1_000_000_000 / 2))
    return playhead_ns - half, playhead_ns + half


class ProfessionalTimeline(tk.Canvas):
    """Smooth fixed-playhead timeline.

    The detail ruler moves beneath a fixed centre playhead. Canvas items are pooled
    and repositioned rather than deleted and recreated on every refresh. This is
    deliberately less theatrical than the old two-ruler implementation and much
    cheaper for Tk to redraw at video-rate.
    """

    HEADER_H = 35
    DETAIL_TOP = 38
    DETAIL_BOTTOM = 104
    OVERVIEW_TOP = 113
    OVERVIEW_BOTTOM = 136
    SIDE_PAD = 16
    MAX_MAJOR_TICKS = 36
    MAX_MINOR_TICKS = 180
    MAX_MARKERS = 48
    MAX_OVERVIEW_TICKS = 24

    def __init__(
        self,
        master,
        palette: dict[str, str],
        on_seek: Callable[[int], None],
        detail_window_seconds: float = 60.0,
        min_detail_seconds: float = 1.0,
        max_detail_seconds: float = 3600.0,
        on_zoom_commit: Callable[[float], None] | None = None,
        language: str = "en",
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            height=154,
            background=palette["surface"],
            highlightthickness=1,
            highlightbackground=palette["border"],
            takefocus=False,
            **kwargs,
        )
        self.palette = palette
        self.language = normalize_language(language)
        self.on_seek = on_seek
        self.on_zoom_commit = on_zoom_commit
        self.model: TimelineModel | None = None
        self.detail_seconds = detail_window_seconds
        self.min_detail_seconds = min_detail_seconds
        self.max_detail_seconds = max_detail_seconds
        # Kept for compatibility with code that resets it when an attempt changes.
        self.detail_center_ns: int | None = None

        self._render_pending = False
        self._render_suspended = False
        self._dirty_while_suspended = False
        self._last_size = (0, 0)
        self._last_render_perf = 0.0
        self._drag_region: str | None = None
        self._drag_start_x = 0
        self._drag_start_playhead_ns = 0
        self._queued_seek_ns: int | None = None
        self._seek_job: str | None = None
        self._zoom_dragging = False
        self._zoom_commit_job: str | None = None
        self._return_animation_job: str | None = None
        self._animated_playhead_ns: int | None = None

        self._create_item_pool()
        bind_resize_only(self, self._on_configure)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._wheel_linux(e, 1))
        self.bind("<Button-5>", lambda e: self._wheel_linux(e, -1))

    @property
    def fixed_playhead_x(self) -> float:
        return max(self.SIDE_PAD + 1, self.winfo_width() / 2)

    def _create_item_pool(self) -> None:
        p = self.palette
        self._items: dict[str, int] = {}
        self._items["background"] = self.create_rectangle(0, 0, 1, 1, fill=p["surface"], outline="")
        self._items["mode"] = self.create_text(self.SIDE_PAD, 10, anchor="w", text=tr(self.language, "timeline.title"), fill=p["muted"], font=("Segoe UI Semibold", 9))
        self._items["timecode"] = self.create_text(1, 11, anchor="center", text="+0.000s", fill=p["text"], font=("Consolas", 10, "bold"))
        self._items["zoom"] = self.create_text(1, 9, anchor="e", text=format_timeline_span(self.detail_seconds), fill=p["muted"], font=("Segoe UI", 8))
        self._items["zoom_track"] = self.create_line(1, 27, 2, 27, fill=p["border"], width=4)
        self._items["zoom_thumb"] = self.create_oval(1, 22, 2, 32, fill=p["accent"], outline=p["accent"])

        legend_x = self.SIDE_PAD
        for key, colour, label_key in (
            ("recorded", p["recorded"], "timeline.recorded"),
            ("assist", p["assist"], "timeline.assist_scan"),
            ("prediction", p["prediction"], "timeline.prediction"),
        ):
            self._items[f"legend_{key}_swatch"] = self.create_rectangle(legend_x, 22, legend_x + 9, 29, fill=colour, outline="")
            self._items[f"legend_{key}_label"] = self.create_text(legend_x + 13, 25, anchor="w", text=tr(self.language, label_key), fill=p["muted"], font=("Segoe UI", 8))
            legend_x += 82 if key != "prediction" else 0

        self._items["detail_bg"] = self.create_rectangle(1, self.DETAIL_TOP, 2, self.DETAIL_BOTTOM, fill=p["timeline"], outline=p["border"])
        self._items["detail_available"] = self.create_rectangle(1, self.DETAIL_TOP + 25, 2, self.DETAIL_BOTTOM - 5, fill=p["recorded"], outline="")
        self._items["unavailable_left"] = self.create_rectangle(1, self.DETAIL_TOP + 1, 1, self.DETAIL_BOTTOM - 1, fill=p["bg"], outline="", stipple="gray50")
        self._items["unavailable_right"] = self.create_rectangle(1, self.DETAIL_TOP + 1, 1, self.DETAIL_BOTTOM - 1, fill=p["bg"], outline="", stipple="gray50")
        self._items["freeze_line"] = self.create_line(0, 0, 0, 0, fill=p["warning"], width=2, state="hidden")
        self._items["freeze_label"] = self.create_text(0, 0, anchor="s", text=tr(self.language, "timeline.freeze"), fill=p["warning"], font=("Segoe UI Semibold", 8), state="hidden")
        self._items["record_start_line"] = self.create_line(0, 0, 0, 0, fill=p["recorded"], width=2, state="hidden")
        self._items["record_end_line"] = self.create_line(0, 0, 0, 0, fill=p["recorded"], width=2, state="hidden")
        self._items["record_start_label"] = self.create_text(0, 0, anchor="se", text="", fill=p["text"], font=("Consolas", 7), state="hidden")
        self._items["record_end_label"] = self.create_text(0, 0, anchor="sw", text="", fill=p["text"], font=("Consolas", 7), state="hidden")
        self._items["assist_band"] = self.create_rectangle(0, 0, 0, 0, fill=p["assist"], outline="", stipple="gray50", state="hidden")
        self._items["confidence_band"] = self.create_rectangle(0, 0, 0, 0, fill=p["prediction"], outline=p["prediction"], state="hidden")
        self._items["prediction_line"] = self.create_line(0, 0, 0, 0, fill=p["prediction"], width=2, state="hidden")
        self._items["prediction_diamond"] = self.create_polygon(0, 0, 0, 0, fill=p["prediction"], outline="", state="hidden")
        self._items["prediction_label"] = self.create_text(0, 0, anchor="s", text="", fill=p["prediction"], font=("Segoe UI Semibold", 8), state="hidden")

        self._items["overview_bg"] = self.create_rectangle(1, self.OVERVIEW_TOP, 2, self.OVERVIEW_BOTTOM, fill=p["timeline"], outline=p["border"])
        self._items["overview_available"] = self.create_rectangle(1, self.OVERVIEW_TOP + 3, 2, self.OVERVIEW_BOTTOM - 3, fill=p["recorded"], outline="")
        self._items["overview_viewport"] = self.create_rectangle(1, self.OVERVIEW_TOP + 1, 2, self.OVERVIEW_BOTTOM - 1, fill="", outline=p["text"], width=1)
        self._items["overview_playhead"] = self.create_line(0, self.OVERVIEW_TOP, 0, self.OVERVIEW_BOTTOM, fill=p["danger"], width=2)
        self._items["overview_freeze"] = self.create_line(0, self.OVERVIEW_TOP, 0, self.OVERVIEW_BOTTOM, fill=p["warning"], width=1, state="hidden")
        self._items["overview_assist"] = self.create_rectangle(0, 0, 0, 0, fill=p["assist"], outline="", state="hidden")
        self._items["overview_prediction"] = self.create_line(0, 0, 0, 0, fill=p["prediction"], width=2, state="hidden")
        self._items["focus_band"] = self.create_rectangle(0, self.DETAIL_TOP + 1, 0, self.DETAIL_BOTTOM - 1, fill=p["selection"], outline="", stipple="gray50")

        # The detail playhead is intentionally always centred and created last.
        self._items["fixed_playhead"] = self.create_line(0, self.HEADER_H, 0, self.OVERVIEW_TOP - 2, fill=p["playhead"], width=2)
        self._items["playhead_cap"] = self.create_polygon(0, self.HEADER_H, 0, self.HEADER_H, 0, self.HEADER_H + 7, fill=p["playhead"], outline="")

        self._major_lines = [self.create_line(0, 0, 0, 0, fill=p["tick"], state="hidden") for _ in range(self.MAX_MAJOR_TICKS)]
        self._major_labels = [self.create_text(0, 0, anchor="n", text="", fill=p["muted"], font=("Consolas", 7), state="hidden") for _ in range(self.MAX_MAJOR_TICKS)]
        self._minor_lines = [self.create_line(0, 0, 0, 0, fill=p["border"], state="hidden") for _ in range(self.MAX_MINOR_TICKS)]
        self._marker_lines = [self.create_line(0, 0, 0, 0, fill=p["accent_hover"], dash=(2, 2), state="hidden") for _ in range(self.MAX_MARKERS)]
        self._overview_ticks = [self.create_line(0, 0, 0, 0, fill=p["tick"], state="hidden") for _ in range(self.MAX_OVERVIEW_TICKS)]

    def set_language(self, language: str) -> None:
        self.language = normalize_language(language)
        self.itemconfigure(self._items["freeze_label"], text=tr(self.language, "timeline.freeze"))
        for key, label_key in (("recorded", "timeline.recorded"), ("assist", "timeline.assist_scan"), ("prediction", "timeline.prediction")):
            self.itemconfigure(self._items[f"legend_{key}_label"], text=tr(self.language, label_key))
        self.request_render(force=True)

    def apply_palette(self, palette: dict[str, str]) -> None:
        self.palette = palette
        self.configure(background=palette["surface"], highlightbackground=palette["border"])
        self._apply_item_colours()
        self.request_render(force=True)

    def _apply_item_colours(self) -> None:
        p = self.palette
        self.itemconfigure(self._items["background"], fill=p["surface"])
        self.itemconfigure(self._items["mode"], fill=p["muted"])
        self.itemconfigure(self._items["timecode"], fill=p["text"])
        self.itemconfigure(self._items["zoom"], fill=p["muted"])
        self.itemconfigure(self._items["zoom_track"], fill=p["border"])
        self.itemconfigure(self._items["zoom_thumb"], fill=p["accent"], outline=p["accent"])
        self.itemconfigure(self._items["detail_bg"], fill=p["timeline"], outline=p["border"])
        self.itemconfigure(self._items["detail_available"], fill=p["recorded"])
        self.itemconfigure(self._items["unavailable_left"], fill=p["bg"])
        self.itemconfigure(self._items["unavailable_right"], fill=p["bg"])
        self.itemconfigure(self._items["freeze_line"], fill=p["warning"])
        self.itemconfigure(self._items["freeze_label"], fill=p["warning"])
        for name in ("record_start_line", "record_end_line"):
            self.itemconfigure(self._items[name], fill=p["recorded"])
        for name in ("record_start_label", "record_end_label"):
            self.itemconfigure(self._items[name], fill=p["text"])
        self.itemconfigure(self._items["assist_band"], fill=p["assist"])
        self.itemconfigure(self._items["confidence_band"], fill=p["prediction"], outline=p["prediction"])
        for name in ("prediction_line", "prediction_diamond", "prediction_label"):
            self.itemconfigure(self._items[name], fill=p["prediction"])
        for key in ("recorded", "assist", "prediction"):
            self.itemconfigure(self._items[f"legend_{key}_swatch"], fill=p[key])
            self.itemconfigure(self._items[f"legend_{key}_label"], fill=p["muted"])
        self.itemconfigure(self._items["overview_bg"], fill=p["timeline"], outline=p["border"])
        self.itemconfigure(self._items["overview_available"], fill=p["recorded"])
        self.itemconfigure(self._items["overview_viewport"], outline=p["text"])
        self.itemconfigure(self._items["overview_playhead"], fill=p["danger"])
        self.itemconfigure(self._items["overview_freeze"], fill=p["warning"])
        self.itemconfigure(self._items["overview_assist"], fill=p["assist"])
        self.itemconfigure(self._items["overview_prediction"], fill=p["prediction"])
        self.itemconfigure(self._items["focus_band"], fill=p["selection"])
        self.itemconfigure(self._items["fixed_playhead"], fill=p["playhead"])
        self.itemconfigure(self._items["playhead_cap"], fill=p["playhead"])
        for item in self._major_lines:
            self.itemconfigure(item, fill=p["tick"])
        for item in self._major_labels:
            self.itemconfigure(item, fill=p["muted"])
        for item in self._minor_lines:
            self.itemconfigure(item, fill=p["border"])
        for item in self._marker_lines:
            self.itemconfigure(item, fill=p["accent_hover"])
        for item in self._overview_ticks:
            self.itemconfigure(item, fill=p["tick"])

    def set_model(self, model: TimelineModel | None) -> None:
        self.model = model
        self.request_render()

    def set_render_suspended(self, suspended: bool) -> None:
        if self._render_suspended == suspended:
            return
        self._render_suspended = suspended
        if not suspended and self._dirty_while_suspended:
            self._dirty_while_suspended = False
            self.request_render(force=True)

    def request_render(self, force: bool = False) -> None:
        if self._render_suspended:
            self._dirty_while_suspended = True
            return
        if self._render_pending and not force:
            return
        if self._render_pending and force:
            return
        self._render_pending = True
        try:
            # after_idle coalesces many 120-fps model updates into one GUI draw.
            self.after_idle(self._render)
        except tk.TclError:
            self._render_pending = False

    def redraw(self) -> None:
        self.request_render(force=True)

    def animate_return_to_live(self) -> None:
        """Ease the detail ruler from the frozen frame back to live media."""
        if self.model is None:
            self.detail_center_ns = None
            return
        self._animated_playhead_ns = int(self.model.playhead_ns)
        if self._return_animation_job is not None:
            try:
                self.after_cancel(self._return_animation_job)
            except tk.TclError:
                pass
        self._return_animation_step()

    def _return_animation_step(self) -> None:
        self._return_animation_job = None
        if self.model is None or self._animated_playhead_ns is None:
            self._animated_playhead_ns = None
            self.request_render(force=True)
            return
        target = int(self.model.playhead_ns)
        current = self._animated_playhead_ns
        remaining = target - current
        if abs(remaining) <= 2_000_000:
            self._animated_playhead_ns = None
            self.request_render(force=True)
            return
        self._animated_playhead_ns = int(current + remaining * .24)
        self.request_render(force=True)
        try:
            self._return_animation_job = self.after(16, self._return_animation_step)
        except tk.TclError:
            self._animated_playhead_ns = None

    def _on_configure(self, event) -> None:
        size = (event.width, event.height)
        if size != self._last_size:
            self._last_size = size
            self.request_render(force=True)

    def _render(self) -> None:
        self._render_pending = False
        if self._render_suspended:
            self._dirty_while_suspended = True
            return
        self._last_render_perf = time.perf_counter()
        w = max(240, self.winfo_width())
        h = max(150, self.winfo_height())
        x0, x1 = self.SIDE_PAD, w - self.SIDE_PAD
        cx = w / 2
        p = self.palette

        self.coords(self._items["background"], 0, 0, w, h)
        self.coords(self._items["mode"], x0, 10)
        self.coords(self._items["timecode"], cx, 11)
        self.coords(self._items["zoom"], x1, 9)
        zoom_left, zoom_right = self._zoom_track_bounds(w)
        self.coords(self._items["zoom_track"], zoom_left, 27, zoom_right, 27)
        self.coords(self._items["zoom_thumb"], self._zoom_x(zoom_left, zoom_right) - 5, 22, self._zoom_x(zoom_left, zoom_right) + 5, 32)
        self.coords(self._items["detail_bg"], x0, self.DETAIL_TOP, x1, self.DETAIL_BOTTOM)
        self.coords(self._items["overview_bg"], x0, self.OVERVIEW_TOP, x1, self.OVERVIEW_BOTTOM)
        self.coords(self._items["focus_band"], cx - 22, self.DETAIL_TOP + 1, cx + 22, self.DETAIL_BOTTOM - 1)
        self.coords(self._items["fixed_playhead"], cx, self.HEADER_H, cx, self.OVERVIEW_TOP - 2)
        self.coords(self._items["playhead_cap"], cx - 6, self.HEADER_H, cx + 6, self.HEADER_H, cx, self.HEADER_H + 7)
        self.tag_raise(self._items["fixed_playhead"])
        self.tag_raise(self._items["playhead_cap"])

        model = self.model
        if model is None or model.end_ns <= model.start_ns:
            self.itemconfigure(self._items["mode"], text=tr(self.language, "timeline.title"))
            self.itemconfigure(self._items["timecode"], text=tr(self.language, "timeline.waiting"))
            self.itemconfigure(self._items["zoom"], text=format_timeline_span(self.detail_seconds))
            self.coords(self._items["detail_available"], x0 + 1, self.DETAIL_TOP + 25, x0 + 1, self.DETAIL_BOTTOM - 5)
            self.coords(self._items["overview_available"], x0 + 1, self.OVERVIEW_TOP + 3, x0 + 1, self.OVERVIEW_BOTTOM - 3)
            self._hide_pools()
            return

        playhead = self._animated_playhead_ns if self._animated_playhead_ns is not None else model.playhead_ns
        detail_start, detail_end = centered_window(playhead, self.detail_seconds)
        rel = (playhead - model.reference_ns) / 1e9
        mode_text = tr(self.language, "timeline.live_buffer") if model.is_live else (tr(self.language, "timeline.attempt_review") if model.freeze_ns is not None else tr(self.language, "timeline.buffer_review"))
        self.itemconfigure(self._items["mode"], text=mode_text)
        wall = model.wall_start_ns + max(0, playhead - model.start_ns) if model.wall_start_ns else 0
        self.itemconfigure(self._items["timecode"], text=format_wall_time_ns(wall) if wall else format_relative(rel, True))
        self.itemconfigure(self._items["zoom"], text=format_timeline_span(self.detail_seconds))

        # Available media is painted once as a broad band; unavailable space is dimmed.
        available_start = model.available_start_ns if model.available_start_ns is not None else model.start_ns
        available_end = model.available_end_ns if model.available_end_ns is not None else model.end_ns
        ax0 = self._time_to_x(available_start, detail_start, detail_end, x0, x1)
        ax1 = self._time_to_x(available_end, detail_start, detail_end, x0, x1)
        ax0c, ax1c = max(x0, min(x1, ax0)), max(x0, min(x1, ax1))
        self.coords(self._items["detail_available"], ax0c, self.DETAIL_TOP + 25, ax1c, self.DETAIL_BOTTOM - 5)
        self.coords(self._items["unavailable_left"], x0 + 1, self.DETAIL_TOP + 1, max(x0 + 1, ax0c), self.DETAIL_BOTTOM - 1)
        self.coords(self._items["unavailable_right"], min(x1 - 1, ax1c), self.DETAIL_TOP + 1, x1 - 1, self.DETAIL_BOTTOM - 1)

        self._render_detail_ticks(model, detail_start, detail_end, x0, x1)
        self._render_markers(model, detail_start, detail_end, x0, x1)
        self._render_recording_bounds(model, detail_start, detail_end, x0, x1)
        self._render_assist(model, detail_start, detail_end, x0, x1)
        self._render_prediction(model, detail_start, detail_end, x0, x1)
        self._render_freeze(model, detail_start, detail_end, x0, x1)
        self._render_overview(model, detail_start, detail_end, x0, x1)

        self.tag_raise(self._items["fixed_playhead"])
        self.tag_raise(self._items["playhead_cap"])

    def _render_detail_ticks(self, model: TimelineModel, start_ns: int, end_ns: int, x0: float, x1: float) -> None:
        duration = (end_ns - start_ns) / 1e9
        step = choose_tick_step(duration, int(x1 - x0), 92)
        minor_count = 5
        start_rel = (start_ns - model.reference_ns) / 1e9
        end_rel = (end_ns - model.reference_ns) / 1e9
        first = math.floor(start_rel / step) * step

        major_i = 0
        minor_i = 0
        t = first
        while t <= end_rel + step and major_i < self.MAX_MAJOR_TICKS:
            ts = model.reference_ns + int(round(t * 1e9))
            x = self._time_to_x(ts, start_ns, end_ns, x0, x1)
            if x0 - 2 <= x <= x1 + 2:
                line = self._major_lines[major_i]
                label = self._major_labels[major_i]
                self.coords(line, x, self.DETAIL_TOP + 1, x, self.DETAIL_TOP + 14)
                self.coords(label, x, self.DETAIL_TOP + 16)
                self.itemconfigure(line, state="normal")
                if x0 + 31 <= x <= x1 - 31:
                    wall = model.wall_start_ns + max(0, ts - model.start_ns) if model.wall_start_ns else 0
                    self.itemconfigure(label, state="normal", text=format_wall_time_ns(wall) if wall else format_relative(t, duration <= 4.0))
                else:
                    self.itemconfigure(label, state="hidden")
                major_i += 1
            for i in range(1, minor_count):
                mt = t + step * i / minor_count
                if mt > end_rel + 1e-9 or minor_i >= self.MAX_MINOR_TICKS:
                    break
                mts = model.reference_ns + int(round(mt * 1e9))
                mx = self._time_to_x(mts, start_ns, end_ns, x0, x1)
                if x0 <= mx <= x1:
                    item = self._minor_lines[minor_i]
                    self.coords(item, mx, self.DETAIL_BOTTOM - 8, mx, self.DETAIL_BOTTOM - 2)
                    self.itemconfigure(item, state="normal")
                    minor_i += 1
            t += step
        self._hide_from(self._major_lines, major_i)
        self._hide_from(self._major_labels, major_i)
        self._hide_from(self._minor_lines, minor_i)

    def _render_markers(self, model: TimelineModel, start_ns: int, end_ns: int, x0: float, x1: float) -> None:
        count = 0
        for marker in model.markers_ns:
            if start_ns <= marker <= end_ns and count < self.MAX_MARKERS:
                x = self._time_to_x(marker, start_ns, end_ns, x0, x1)
                item = self._marker_lines[count]
                self.coords(item, x, self.DETAIL_TOP + 10, x, self.DETAIL_BOTTOM - 2)
                self.itemconfigure(item, state="normal")
                count += 1
        self._hide_from(self._marker_lines, count)

    def _render_recording_bounds(self, model: TimelineModel, start_ns: int, end_ns: int, x0: float, x1: float) -> None:
        available_start = model.available_start_ns if model.available_start_ns is not None else model.start_ns
        available_end = model.available_end_ns if model.available_end_ns is not None else model.end_ns
        visible: list[tuple[str, float]] = []
        for name, timestamp, anchor in (
            ("record_start", available_start, "se"),
            ("record_end", available_end, "sw"),
        ):
            if not start_ns <= timestamp <= end_ns:
                self.itemconfigure(self._items[f"{name}_line"], state="hidden")
                self.itemconfigure(self._items[f"{name}_label"], state="hidden")
                continue
            x = self._time_to_x(timestamp, start_ns, end_ns, x0, x1)
            wall = model.wall_start_ns + max(0, timestamp - model.start_ns) if model.wall_start_ns else 0
            text = format_wall_time_ns(wall) if wall else format_relative((timestamp - model.reference_ns) / 1e9, True)
            self.coords(self._items[f"{name}_line"], x, self.DETAIL_TOP + 23, x, self.DETAIL_BOTTOM - 3)
            self.coords(self._items[f"{name}_label"], x - 3 if anchor == "se" else x + 3, self.DETAIL_BOTTOM - 7)
            self.itemconfigure(self._items[f"{name}_label"], text=text, anchor=anchor, state="normal")
            self.itemconfigure(self._items[f"{name}_line"], state="normal")
            visible.append((name, x))
        if len(visible) == 2 and abs(visible[1][1] - visible[0][1]) < 150:
            # Short clips remain readable at the one-minute minimum by using two label rows.
            self.coords(self._items["record_start_label"], visible[0][1] - 3, self.DETAIL_BOTTOM - 7)
            self.coords(self._items["record_end_label"], visible[1][1] + 3, self.DETAIL_TOP + 39)

    def _render_assist(self, model: TimelineModel, start_ns: int, end_ns: int, x0: float, x1: float) -> None:
        if model.assist_start_ns is None or model.assist_end_ns is None:
            self.itemconfigure(self._items["assist_band"], state="hidden")
            return
        visible_start = max(start_ns, model.assist_start_ns)
        visible_end = min(end_ns, model.assist_end_ns)
        if visible_start > visible_end:
            self.itemconfigure(self._items["assist_band"], state="hidden")
            return
        left = self._time_to_x(visible_start, start_ns, end_ns, x0, x1)
        right = self._time_to_x(visible_end, start_ns, end_ns, x0, x1)
        self.coords(self._items["assist_band"], left, self.DETAIL_TOP + 29, right, self.DETAIL_BOTTOM - 9)
        self.itemconfigure(self._items["assist_band"], state="normal")

    def _render_prediction(self, model: TimelineModel, start_ns: int, end_ns: int, x0: float, x1: float) -> None:
        timestamp = model.predicted_frame_ns
        names = ("confidence_band", "prediction_line", "prediction_diamond", "prediction_label")
        if timestamp is None or not start_ns <= timestamp <= end_ns:
            for name in names:
                self.itemconfigure(self._items[name], state="hidden")
            return
        x = self._time_to_x(timestamp, start_ns, end_ns, x0, x1)
        zone_start = max(start_ns, timestamp - 100_000_000)
        zone_end = min(end_ns, timestamp + 100_000_000)
        left = self._time_to_x(zone_start, start_ns, end_ns, x0, x1)
        right = self._time_to_x(zone_end, start_ns, end_ns, x0, x1)
        if right - left < 8:
            left, right = x - 4, x + 4
        confidence = max(0.0, min(1.0, model.prediction_confidence))
        stipple = "gray25" if confidence < .34 else ("gray50" if confidence < .67 else "gray75")
        self.coords(self._items["confidence_band"], left, self.DETAIL_TOP + 25, right, self.DETAIL_BOTTOM - 5)
        self.itemconfigure(self._items["confidence_band"], stipple=stipple, state="normal")
        self.coords(self._items["prediction_line"], x, self.DETAIL_TOP + 20, x, self.DETAIL_BOTTOM - 3)
        self.coords(
            self._items["prediction_diamond"],
            x, self.DETAIL_TOP + 20, x + 5, self.DETAIL_TOP + 25,
            x, self.DETAIL_TOP + 30, x - 5, self.DETAIL_TOP + 25,
        )
        self.coords(self._items["prediction_label"], x, self.DETAIL_TOP + 42)
        self.itemconfigure(self._items["prediction_label"], text=f"{tr(self.language, 'timeline.prediction')} {confidence:.0%}", state="normal")
        for name in ("prediction_line", "prediction_diamond"):
            self.itemconfigure(self._items[name], state="normal")

    def _render_freeze(self, model: TimelineModel, start_ns: int, end_ns: int, x0: float, x1: float) -> None:
        if model.freeze_ns is None or not (start_ns <= model.freeze_ns <= end_ns):
            self.itemconfigure(self._items["freeze_line"], state="hidden")
            self.itemconfigure(self._items["freeze_label"], state="hidden")
            return
        x = self._time_to_x(model.freeze_ns, start_ns, end_ns, x0, x1)
        self.coords(self._items["freeze_line"], x, self.DETAIL_TOP + 1, x, self.DETAIL_BOTTOM - 1)
        self.coords(self._items["freeze_label"], x, self.DETAIL_BOTTOM - 2)
        self.itemconfigure(self._items["freeze_line"], state="normal")
        self.itemconfigure(self._items["freeze_label"], state="normal")

    def _render_overview(self, model: TimelineModel, detail_start: int, detail_end: int, x0: float, x1: float) -> None:
        full_start, full_end = model.start_ns, max(model.start_ns + 1, model.end_ns)
        available_start = model.available_start_ns if model.available_start_ns is not None else full_start
        available_end = model.available_end_ns if model.available_end_ns is not None else full_end
        av0 = self._time_to_x(available_start, full_start, full_end, x0, x1)
        av1 = self._time_to_x(available_end, full_start, full_end, x0, x1)
        self.coords(self._items["overview_available"], max(x0 + 1, av0), self.OVERVIEW_TOP + 4, min(x1 - 1, av1), self.OVERVIEW_BOTTOM - 4)

        if model.assist_start_ns is not None and model.assist_end_ns is not None:
            assist_start = max(full_start, model.assist_start_ns)
            assist_end = min(full_end, model.assist_end_ns)
            if assist_start <= assist_end:
                aa0 = self._time_to_x(assist_start, full_start, full_end, x0, x1)
                aa1 = self._time_to_x(assist_end, full_start, full_end, x0, x1)
                self.coords(self._items["overview_assist"], aa0, self.OVERVIEW_TOP + 7, aa1, self.OVERVIEW_BOTTOM - 7)
                self.itemconfigure(self._items["overview_assist"], state="normal")
            else:
                self.itemconfigure(self._items["overview_assist"], state="hidden")
        else:
            self.itemconfigure(self._items["overview_assist"], state="hidden")
        if model.predicted_frame_ns is not None and full_start <= model.predicted_frame_ns <= full_end:
            prediction_x = self._time_to_x(model.predicted_frame_ns, full_start, full_end, x0, x1)
            self.coords(self._items["overview_prediction"], prediction_x, self.OVERVIEW_TOP + 2, prediction_x, self.OVERVIEW_BOTTOM - 2)
            self.itemconfigure(self._items["overview_prediction"], state="normal")
        else:
            self.itemconfigure(self._items["overview_prediction"], state="hidden")

        vx0 = self._time_to_x(detail_start, full_start, full_end, x0, x1)
        vx1 = self._time_to_x(detail_end, full_start, full_end, x0, x1)
        self.coords(self._items["overview_viewport"], max(x0, vx0), self.OVERVIEW_TOP + 1, min(x1, vx1), self.OVERVIEW_BOTTOM - 1)
        px = self._time_to_x(model.playhead_ns, full_start, full_end, x0, x1)
        self.coords(self._items["overview_playhead"], px, self.OVERVIEW_TOP, px, self.OVERVIEW_BOTTOM)

        if model.freeze_ns is not None and full_start <= model.freeze_ns <= full_end:
            fx = self._time_to_x(model.freeze_ns, full_start, full_end, x0, x1)
            self.coords(self._items["overview_freeze"], fx, self.OVERVIEW_TOP + 1, fx, self.OVERVIEW_BOTTOM - 1)
            self.itemconfigure(self._items["overview_freeze"], state="normal")
        else:
            self.itemconfigure(self._items["overview_freeze"], state="hidden")

        duration = (full_end - full_start) / 1e9
        step = choose_tick_step(duration, int(x1 - x0), 140)
        first = math.ceil(((full_start - model.reference_ns) / 1e9) / step) * step
        end_rel = (full_end - model.reference_ns) / 1e9
        i = 0
        t = first
        while t <= end_rel + 1e-9 and i < self.MAX_OVERVIEW_TICKS:
            ts = model.reference_ns + int(round(t * 1e9))
            x = self._time_to_x(ts, full_start, full_end, x0, x1)
            item = self._overview_ticks[i]
            self.coords(item, x, self.OVERVIEW_TOP + 1, x, self.OVERVIEW_TOP + 5)
            self.itemconfigure(item, state="normal")
            i += 1
            t += step
        self._hide_from(self._overview_ticks, i)

    def _hide_pools(self) -> None:
        for pool in (self._major_lines, self._major_labels, self._minor_lines, self._marker_lines, self._overview_ticks):
            self._hide_from(pool, 0)
        for name in (
            "freeze_line", "freeze_label", "overview_freeze", "record_start_line", "record_end_line",
            "record_start_label", "record_end_label", "assist_band", "confidence_band", "prediction_line",
            "prediction_diamond", "prediction_label", "overview_assist", "overview_prediction",
        ):
            self.itemconfigure(self._items[name], state="hidden")

    def _hide_from(self, items: list[int], start: int) -> None:
        for item in items[start:]:
            self.itemconfigure(item, state="hidden")

    @staticmethod
    def _time_to_x(timestamp_ns: int, start_ns: int, end_ns: int, x0: float, x1: float) -> float:
        return x0 + (timestamp_ns - start_ns) / max(1, end_ns - start_ns) * (x1 - x0)

    @staticmethod
    def _x_to_time(x: float, start_ns: int, end_ns: int, x0: float, x1: float) -> int:
        fraction = max(0.0, min(1.0, (x - x0) / max(1.0, x1 - x0)))
        return start_ns + int(fraction * (end_ns - start_ns))

    def _region_for_y(self, y: int) -> str | None:
        if self.DETAIL_TOP <= y <= self.DETAIL_BOTTOM:
            return "detail"
        if self.OVERVIEW_TOP - 4 <= y <= self.OVERVIEW_BOTTOM + 4:
            return "overview"
        return None

    def _on_press(self, event) -> str:
        model = self.model
        if self._zoom_region(event.x, event.y):
            self._zoom_dragging = True
            self._set_zoom_from_x(event.x)
            return "break"
        region = self._region_for_y(event.y)
        if model is None or region is None:
            return "break"
        self._drag_region = region
        self._drag_start_x = event.x
        self._drag_start_playhead_ns = model.playhead_ns
        if region == "overview":
            self._queue_seek(self._overview_time_at(event.x))
        else:
            # A click jumps to the time under the cursor. A subsequent drag uses
            # fixed-playhead scrubbing, which avoids the old elastic cursor feel.
            detail_start, detail_end = centered_window(model.playhead_ns, self.detail_seconds)
            target = self._x_to_time(event.x, detail_start, detail_end, self.SIDE_PAD, self.winfo_width() - self.SIDE_PAD)
            self._queue_seek(self._clamp_to_media(target))
        return "break"

    def _on_drag(self, event) -> str:
        model = self.model
        if self._zoom_dragging:
            self._set_zoom_from_x(event.x)
            return "break"
        if model is None or self._drag_region is None:
            return "break"
        if self._drag_region == "overview":
            self._queue_seek(self._overview_time_at(event.x))
        else:
            usable = max(1, self.winfo_width() - 2 * self.SIDE_PAD)
            delta_seconds = (event.x - self._drag_start_x) / usable * self.detail_seconds
            target = self._drag_start_playhead_ns + int(delta_seconds * 1e9)
            self._queue_seek(self._clamp_to_media(target))
        return "break"

    def _on_release(self, _event) -> str:
        commit_zoom = self._zoom_dragging
        self._drag_region = None
        self._zoom_dragging = False
        if commit_zoom:
            self._commit_zoom()
        return "break"

    def _zoom_bounds(self) -> tuple[float, float]:
        return self.min_detail_seconds, self.max_detail_seconds

    def _zoom_track_bounds(self, width: int | None = None) -> tuple[float, float]:
        width = width or self.winfo_width()
        right = width - self.SIDE_PAD - 2
        left = max(self.SIDE_PAD + 150, right - 180)
        return min(left, right - 40), right

    def _zoom_x(self, left: float, right: float) -> float:
        low, high = self._zoom_bounds()
        value = math.log(max(low, min(high, self.detail_seconds)) / low) / max(1e-9, math.log(high / low))
        return left + value * (right - left)

    def _zoom_region(self, x: int, y: int) -> bool:
        if not 19 <= y <= 35:
            return False
        left, right = self._zoom_track_bounds()
        return left - 10 <= x <= right + 10

    def _set_zoom_from_x(self, x: int) -> None:
        left, right = self._zoom_track_bounds()
        fraction = max(0.0, min(1.0, (x - left) / max(1.0, right - left)))
        low, high = self._zoom_bounds()
        self.detail_seconds = low * ((high / low) ** fraction)
        self.request_render(force=True)

    def _overview_time_at(self, x: int) -> int:
        assert self.model is not None
        return self._x_to_time(x, self.model.start_ns, self.model.end_ns, self.SIDE_PAD, self.winfo_width() - self.SIDE_PAD)

    def _clamp_to_media(self, timestamp_ns: int) -> int:
        if self.model is None:
            return timestamp_ns
        start = self.model.available_start_ns if self.model.available_start_ns is not None else self.model.start_ns
        end = self.model.available_end_ns if self.model.available_end_ns is not None else self.model.end_ns
        return max(start, min(end, timestamp_ns))

    def _queue_seek(self, timestamp_ns: int) -> None:
        self._queued_seek_ns = timestamp_ns
        if self._seek_job is not None:
            return
        try:
            self._seek_job = self.after_idle(self._flush_seek)
        except tk.TclError:
            self._seek_job = None

    def _flush_seek(self) -> None:
        self._seek_job = None
        timestamp = self._queued_seek_ns
        self._queued_seek_ns = None
        if timestamp is not None:
            self.on_seek(timestamp)

    def _on_double_click(self, _event) -> str:
        if self.model and self.model.freeze_ns is not None:
            self._queue_seek(self.model.freeze_ns)
        return "break"

    def _on_wheel(self, event) -> str:
        # Fixed-centre zoom. There is no detached detail centre to lose track of.
        factor = .82 if event.delta > 0 else 1.22
        self.detail_seconds = max(self.min_detail_seconds, min(self.max_detail_seconds, self.detail_seconds * factor))
        self.request_render(force=True)
        self._schedule_zoom_commit()
        return "break"

    def _schedule_zoom_commit(self) -> None:
        if self._zoom_commit_job is not None:
            try:
                self.after_cancel(self._zoom_commit_job)
            except tk.TclError:
                pass
        try:
            self._zoom_commit_job = self.after(250, self._commit_zoom)
        except tk.TclError:
            self._zoom_commit_job = None

    def _commit_zoom(self) -> None:
        self._zoom_commit_job = None
        if self.on_zoom_commit is not None:
            self.on_zoom_commit(self.detail_seconds)

    def _wheel_linux(self, event, direction: int) -> str:
        event.delta = 120 * direction
        return self._on_wheel(event)
