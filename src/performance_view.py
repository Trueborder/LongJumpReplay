from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .models import BufferStats, CaptureStats
from .performance_monitor import PerformanceMonitor


class PerformanceView(ttk.Frame):
    """Compact live health dashboard. All history is session-only."""

    METRICS = (
        ("capture_fps", "Camera FPS", "FPS kamery", "{:.1f}"),
        ("encode_fps", "Buffer FPS", "FPS bufferu", "{:.1f}"),
        ("queue_depth", "Encoder queue", "Fronta enkodéru", "{:.0f}"),
        ("queue_drops", "Queue drops", "Výpadky fronty", "{:.0f}"),
        ("read_failures", "Read failures", "Chyby čtení", "{:.0f}"),
        ("encode_failures", "Encode failures", "Chyby enkodéru", "{:.0f}"),
        ("buffer_seconds", "Replay buffer", "Replay buffer", "{:.1f} s"),
        ("buffer_memory_mb", "Buffer RAM", "RAM bufferu", "{:.0f} MB"),
        ("cache_gb", "Attempt cache", "Mezipaměť pokusů", "{:.2f} GB"),
        ("disk_free_gb", "Export free", "Volné místo exportu", "{:.1f} GB"),
        ("ui_p95_ms", "UI p95", "UI p95", "{:.1f} ms"),
        ("cpu_percent", "App CPU", "CPU aplikace", "{:.1f}%"),
        ("process_ram_mb", "App RAM", "RAM aplikace", "{:.0f} MB"),
        ("system_ram_percent", "System RAM", "RAM systému", "{:.1f}%"),
    )

    def __init__(self, parent: tk.Misc, monitor: PerformanceMonitor, palette: dict[str, str], language: str = "en") -> None:
        super().__init__(parent, style="Panel.TFrame", padding=(10, 8))
        self.monitor = monitor
        self.palette = palette
        self.language = language
        self._value_vars: dict[str, tk.StringVar] = {}
        self._metric_labels: dict[str, ttk.Label] = {}
        self._target_fps = 1.0
        self._queue_capacity = 1
        self._source_var = tk.StringVar(value="Collecting data…" if language != "cs" else "Shromažďuji data…")
        self._health_var = tk.StringVar(value="ⓘ  Monitoring starts with the camera" if language != "cs" else "ⓘ  Sledování začne s kamerou")
        self._build()

    def _txt(self, en: str, cs: str) -> str:
        return cs if self.language == "cs" else en

    def _build(self) -> None:
        self.title_label = ttk.Label(self, text=self._txt("Live performance", "Živý výkon"), style="PanelTitle.TLabel")
        self.title_label.pack(anchor="w")
        ttk.Label(self, textvariable=self._source_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 4))
        ttk.Label(self, textvariable=self._health_var, style="Status.TLabel").pack(anchor="w", pady=(0, 8))

        cards = ttk.Frame(self, style="Panel.TFrame")
        cards.pack(fill="x")
        for column in range(2):
            cards.columnconfigure(column, weight=1, uniform="performance-card")
        for index, (key, en, cs, _format) in enumerate(self.METRICS):
            card = ttk.Frame(cards, style="Toolbar.TFrame", padding=(8, 6))
            card.grid(row=index // 2, column=index % 2, sticky="ew", padx=(0 if index % 2 == 0 else 4, 4 if index % 2 == 0 else 0), pady=2)
            label = ttk.Label(card, text=self._txt(en, cs), style="Muted.TLabel")
            label.pack(anchor="w")
            self._metric_labels[key] = label
            value = tk.StringVar(value="—")
            self._value_vars[key] = value
            ttk.Label(card, textvariable=value, style="ContextValue.TLabel").pack(anchor="w", pady=(1, 0))

        graph_host = ttk.Frame(self, style="Panel.TFrame")
        graph_host.pack(fill="both", expand=True, pady=(8, 0))
        graph_host.columnconfigure(0, weight=1)
        graph_host.rowconfigure(1, weight=1)
        self.fps_title = ttk.Label(graph_host, text=self._txt("Camera FPS · target percentage", "FPS kamery · procento cíle"), style="ContextTitle.TLabel")
        self.fps_title.grid(row=0, column=0, sticky="w")
        self.fps_canvas = tk.Canvas(graph_host, height=105, highlightthickness=1, bd=0)
        self.fps_canvas.grid(row=1, column=0, sticky="nsew", pady=(3, 8))
        self.queue_title = ttk.Label(graph_host, text=self._txt("Encoder queue pressure · capacity percentage", "Zatížení fronty enkodéru · procento kapacity"), style="ContextTitle.TLabel")
        self.queue_title.grid(row=2, column=0, sticky="w")
        self.queue_canvas = tk.Canvas(graph_host, height=105, highlightthickness=1, bd=0)
        self.queue_canvas.grid(row=3, column=0, sticky="nsew", pady=(3, 8))
        self.resource_title = ttk.Label(graph_host, text=self._txt("App CPU (blue, %) · App RAM (green, MB)", "CPU aplikace (modrá, %) · RAM aplikace (zelená, MB)"), style="ContextTitle.TLabel")
        self.resource_title.grid(row=4, column=0, sticky="w")
        self.resource_canvas = tk.Canvas(graph_host, height=105, highlightthickness=1, bd=0)
        self.resource_canvas.grid(row=5, column=0, sticky="nsew", pady=(3, 0))
        for canvas in (self.fps_canvas, self.queue_canvas, self.resource_canvas):
            canvas.bind("<Configure>", lambda _event: self.redraw())
        self.apply_palette(self.palette)

    def set_language(self, language: str) -> None:
        self.language = language
        self.title_label.configure(text=self._txt("Live performance", "Živý výkon"))
        for key, en, cs, _template in self.METRICS:
            self._metric_labels[key].configure(text=self._txt(en, cs))
        self.fps_title.configure(text=self._txt("Camera FPS · target percentage", "FPS kamery · procento cíle"))
        self.queue_title.configure(text=self._txt("Encoder queue pressure · capacity percentage", "Zatížení fronty enkodéru · procento kapacity"))
        self.resource_title.configure(text=self._txt("App CPU (blue, %) · App RAM (green, MB)", "CPU aplikace (modrá, %) · RAM aplikace (zelená, MB)"))
        self.redraw()

    def apply_palette(self, palette: dict[str, str]) -> None:
        self.palette = palette
        for canvas in (self.fps_canvas, self.queue_canvas, self.resource_canvas):
            canvas.configure(background=palette["timeline"], highlightbackground=palette["border"])
        self.redraw()

    @staticmethod
    def _triple(current: float, short: float | None, long: float | None, template: str) -> str:
        def shown(value: float | None) -> str:
            return "—" if value is None else template.format(value)
        return f"{shown(current)}  ·  60 s {shown(short)}  ·  10 min {shown(long)}"

    def refresh(self, capture: CaptureStats, buffer: BufferStats, *, target_fps: float, queue_capacity: int) -> None:
        self._target_fps = max(1.0, float(target_fps))
        self._queue_capacity = max(1, int(queue_capacity))
        self._source_var.set(capture.source_description)
        for key, _en, _cs, template in self.METRICS:
            summary = self.monitor.summary(key)
            self._value_vars[key].set(self._triple(summary.current, summary.average_60s, summary.average_10m, template))
        if capture.last_error:
            self._health_var.set(f"✕  {capture.last_error}")
        elif capture.queue_drops or capture.queue_depth > max(8, queue_capacity // 2):
            self._health_var.set(self._txt("⚠  Capture pressure detected — review the graphs", "⚠  Zjištěno zatížení snímání — zkontrolujte grafy"))
        elif capture.captured_frames:
            self._health_var.set(self._txt(
                f"ⓘ  Monitoring {self.monitor.collected_seconds}s · target {target_fps:.1f} FPS",
                f"ⓘ  Sledování {self.monitor.collected_seconds}s · cíl {target_fps:.1f} FPS",
            ))
        self.redraw()

    def redraw(self) -> None:
        samples = list(self.monitor.samples)
        timestamps = [item.monotonic for item in samples]
        self._draw_series(self.fps_canvas, (
            ([min(120.0, item.capture_fps / self._target_fps * 100.0) for item in samples], self.palette["accent"]),
            ([min(120.0, item.encode_fps / self._target_fps * 100.0) for item in samples], self.palette["live"]),
        ), timestamps=timestamps, y_max=120.0)
        self._draw_series(self.queue_canvas, (
            ([min(100.0, float(item.queue_depth) / self._queue_capacity * 100.0) for item in samples], self.palette["warning"]),
        ), timestamps=timestamps, y_max=100.0)
        self._draw_resource_series(samples, timestamps)

    def _draw_resource_series(self, samples: list, timestamps: list[float]) -> None:
        """Draw CPU percentage and process RAM with separate readable axes."""
        canvas = self.resource_canvas
        canvas.delete("all")
        width, height = max(10, canvas.winfo_width()), max(10, canvas.winfo_height())
        left, right, top, bottom = 38, 54, 8, 23
        graph_width = max(1, width - left - right)
        graph_height = max(1, height - top - bottom)
        if timestamps:
            latest = timestamps[-1]
            visible_span = min(600.0, max(1.0, latest - timestamps[0]))
            visible_start = latest - visible_span
        else:
            latest, visible_span, visible_start = 0.0, 1.0, 0.0

        ram_max = max(100.0, max((item.process_ram_mb for item in samples), default=0.0) * 1.1)
        for step in range(5):
            fraction = step / 4
            y = top + graph_height - fraction * graph_height
            canvas.create_line(left, y, width - right, y, fill=self.palette["border"], dash=(2, 4))
            canvas.create_text(left - 5, y, text=f"{fraction * 100:.0f}%", fill=self.palette["muted"], anchor="e", font=("Segoe UI", 8))
            canvas.create_text(width - right + 5, y, text=f"{ram_max * fraction:.0f} MB", fill=self.palette["muted"], anchor="w", font=("Segoe UI", 8))
        left_time = self._elapsed_label(visible_span)
        middle_time = self._elapsed_label(visible_span / 2)
        canvas.create_text(left, height - 7, text=left_time if self.language != "cs" else f"před {left_time.removesuffix(' ago')}", fill=self.palette["muted"], anchor="w", font=("Segoe UI", 8))
        canvas.create_text(left + graph_width / 2, height - 7, text=middle_time if self.language != "cs" else f"před {middle_time.removesuffix(' ago')}", fill=self.palette["muted"], anchor="center", font=("Segoe UI", 8))
        canvas.create_text(width - right, height - 7, text=self._txt("now", "nyní"), fill=self.palette["muted"], anchor="e", font=("Segoe UI", 8))
        if len(samples) < 2:
            canvas.create_text((left + width - right) / 2, (top + height - bottom) / 2, text=self._txt("Collecting data…", "Shromažďuji data…"), fill=self.palette["muted"])
            return

        for values, colour, scale in (
            ([item.cpu_percent for item in samples], self.palette["accent"], 100.0),
            ([item.process_ram_mb for item in samples], self.palette["live"], ram_max),
        ):
            coordinates: list[float] = []
            for index, value in enumerate(values):
                timestamp = timestamps[min(len(timestamps) - 1, index + len(timestamps) - len(values))]
                x = left + max(0.0, min(1.0, (timestamp - visible_start) / visible_span)) * graph_width
                y = top + graph_height - max(0.0, min(scale, value)) / scale * graph_height
                coordinates.extend((x, y))
            canvas.create_line(*coordinates, fill=colour, width=2, smooth=False)

    @staticmethod
    def _elapsed_label(seconds: float) -> str:
        seconds = max(0, int(round(seconds)))
        if seconds < 60:
            return f"{seconds}s ago"
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes}m {remainder:02d}s ago" if remainder else f"{minutes}m ago"

    def _draw_series(
        self,
        canvas: tk.Canvas,
        series: tuple[tuple[list[float], str], ...],
        *,
        timestamps: list[float],
        y_max: float,
    ) -> None:
        canvas.delete("all")
        width, height = max(10, canvas.winfo_width()), max(10, canvas.winfo_height())
        left, right, top, bottom = 38, 8, 8, 23
        graph_width, graph_height = max(1, width - left - right), max(1, height - top - bottom)
        if timestamps:
            latest = timestamps[-1]
            visible_span = min(600.0, max(1.0, latest - timestamps[0]))
            visible_start = latest - visible_span
        else:
            latest, visible_span, visible_start = 0.0, 1.0, 0.0
        ticks = (0, 50, 100, 120) if y_max > 100 else (0, 50, 100)
        for percent in ticks:
            y = top + graph_height - (percent / y_max) * graph_height
            canvas.create_line(left, y, width - right, y, fill=self.palette["border"], dash=(2, 4))
            canvas.create_text(left - 5, y, text=f"{percent}%", fill=self.palette["muted"], anchor="e", font=("Segoe UI", 8))
        left_time = self._elapsed_label(visible_span)
        middle_time = self._elapsed_label(visible_span / 2)
        canvas.create_text(left, height - 7, text=left_time if self.language != "cs" else f"před {left_time.removesuffix(' ago')}", fill=self.palette["muted"], anchor="w", font=("Segoe UI", 8))
        canvas.create_text(left + graph_width / 2, height - 7, text=middle_time if self.language != "cs" else f"před {middle_time.removesuffix(' ago')}", fill=self.palette["muted"], anchor="center", font=("Segoe UI", 8))
        canvas.create_text(width - right, height - 7, text=self._txt("now", "nyní"), fill=self.palette["muted"], anchor="e", font=("Segoe UI", 8))
        values = [value for points, _colour in series for value in points]
        if len(values) < 2:
            canvas.create_text((left + width - right) / 2, (top + height - bottom) / 2, text=self._txt("Collecting data…", "Shromažďuji data…"), fill=self.palette["muted"])
            return
        count = max(len(points) for points, _colour in series)
        for points, colour in series:
            if len(points) < 2:
                continue
            coordinates: list[float] = []
            for index, value in enumerate(points):
                timestamp_index = min(len(timestamps) - 1, index + len(timestamps) - len(points))
                timestamp = timestamps[timestamp_index] if timestamps else latest
                x = left + max(0.0, min(1.0, (timestamp - visible_start) / visible_span)) * graph_width
                y = top + graph_height - max(0.0, min(y_max, value)) / y_max * graph_height
                coordinates.extend((x, y))
            canvas.create_line(*coordinates, fill=colour, width=2, smooth=False)
