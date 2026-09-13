from __future__ import annotations

from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

import cv2
import numpy as np
from PIL import Image, ImageTk

from .i18n import Translator
from .theme import configure_popup
from .top_view_projection import ProjectionCalibration, create_projection_calibration, detect_board_corners, detect_foul_line


def foul_band_from_line(line: Sequence[Sequence[float]], frame_size: tuple[int, int], thickness_px: float = 8.0) -> tuple[tuple[float, float], ...]:
    """Return a normalized four-corner band around a two-point foul line."""
    width, height = frame_size
    points = np.asarray(line, dtype=np.float32).reshape(2, 2)
    vector = points[1] - points[0]
    length = max(1e-6, float(np.linalg.norm(vector)))
    normal = np.asarray([-vector[1], vector[0]], np.float32) / length * max(2.0, float(thickness_px)) * .5
    band = np.asarray((points[0] + normal, points[1] + normal, points[1] - normal, points[0] - normal), np.float32)
    band /= np.asarray([width, height], np.float32)
    return tuple((float(x), float(y)) for x, y in band)


def foul_line_from_band(points: Sequence[Sequence[float]], frame_size: tuple[int, int]) -> tuple[tuple[float, float], ...]:
    """Return source-pixel centreline endpoints from a normalized foul band."""
    width, height = frame_size
    band = np.asarray(points, dtype=np.float32).reshape(4, 2)
    first = (band[0] + band[3]) * .5
    second = (band[1] + band[2]) * .5
    line = np.asarray((first, second), np.float32) * np.asarray([width, height], np.float32)
    return tuple((float(x), float(y)) for x, y in line)


class BoardCalibrationWizard:
    """Startup review of automatically detected board and foul-area geometry."""

    def __init__(
        self,
        master: tk.Misc,
        palette: dict[str, str],
        language: str,
        frame_bgr: np.ndarray,
        roi: Sequence[float],
        camera_signature: str,
        previous: ProjectionCalibration | None,
        previous_foul_area: Sequence[Sequence[float]],
        on_confirm: Callable[[ProjectionCalibration, tuple[tuple[float, float], ...]], None],
        on_close: Callable[[], None],
        current_frame_provider: Callable[[], np.ndarray | None] | None = None,
    ) -> None:
        self.master, self.palette = master, palette
        self.t = Translator(language)
        self.frame = frame_bgr.copy()
        self.frame_size = (self.frame.shape[1], self.frame.shape[0])
        self.roi = tuple(float(value) for value in roi)
        self.camera_signature = camera_signature
        self.previous = previous
        self.previous_foul_area = tuple(tuple(float(value) for value in point) for point in previous_foul_area)
        self.on_confirm, self.on_close = on_confirm, on_close
        self.current_frame_provider = current_frame_provider
        self.board: list[tuple[float, float]] = []
        self.foul_area: list[tuple[float, float]] = []
        self._previous_board: list[tuple[float, float]] = []
        self._previous_foul_area: list[tuple[float, float]] = []
        self._drag_layer = ""
        self._drag_index: int | None = None
        self._closed = False
        self._detect_generation = 0
        self._detect_queue: Queue[tuple[int, object]] = Queue()
        self._photo: ImageTk.PhotoImage | None = None
        self._bounds = (0.0, 0.0, 1.0, 1.0)

        self.window = tk.Toplevel(master)
        configure_popup(self.window, master)
        self.window.title(self.t("calibration.wizard_title"))
        self.window.transient(master)
        self.window.geometry("1040x720")
        self.window.minsize(820, 600)
        self.window.protocol("WM_DELETE_WINDOW", self.skip)
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)

        header = ttk.Frame(self.window, style="Panel.TFrame", padding=(16, 13))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=self.t("calibration.wizard_heading"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text=self.t("calibration.wizard_help"), style="Muted.TLabel", wraplength=900).pack(anchor="w", pady=(4, 0))

        self.canvas = tk.Canvas(self.window, bg=palette["video"], highlightthickness=1, highlightbackground=palette["border"])
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=16)
        self.canvas.bind("<Configure>", lambda _event: self._render())
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)

        footer = ttk.Frame(self.window, style="Panel.TFrame", padding=(16, 12))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=260, style="Modal.Horizontal.TProgressbar")
        self.progress.grid(row=1, column=0, sticky="w")
        self.progress.grid_remove()
        actions = ttk.Frame(footer, style="Panel.TFrame")
        actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.detect_button = ttk.Button(actions, text=self.t("calibration.detect_again"), command=self.detect)
        self.detect_button.pack(side="left", padx=(0, 6))
        self.current_frame_button = ttk.Button(actions, text=self.t("calibration.use_current_frame"), command=self.use_current_frame)
        self.current_frame_button.pack(side="left", padx=(0, 6))
        if self.current_frame_provider is None:
            self.current_frame_button.state(["disabled"])
        self.reset_button = ttk.Button(actions, text=self.t("calibration.reset_previous"), command=self.reset_previous)
        self.reset_button.pack(side="left", padx=(0, 6))
        self.preview_button = ttk.Button(actions, text=self.t("calibration.preview"), style="Primary.TButton", command=self.preview)
        self.preview_button.pack(side="left", padx=(0, 6))
        self.skip_button = ttk.Button(actions, text=self.t("calibration.skip"), command=self.skip)
        self.skip_button.pack(side="left")
        self.back_button = ttk.Button(actions, text=self.t("calibration.back_edit"), command=self.edit)
        self.confirm_button = ttk.Button(actions, text=self.t("calibration.confirm"), style="Primary.TButton", command=self.confirm)

        if previous is not None:
            scale = np.asarray(self.frame_size, np.float32)
            self.board = [tuple(map(float, point)) for point in np.asarray(previous.board_corners, np.float32) * scale]
            if len(self.previous_foul_area) == 4:
                self.foul_area = [tuple(map(float, point)) for point in np.asarray(self.previous_foul_area, np.float32) * scale]
            else:
                line = np.asarray(previous.foul_line, np.float32) * scale
                self.foul_area = [tuple(map(float, point)) for point in np.asarray(foul_band_from_line(line, self.frame_size)) * scale]
            self._previous_board = list(self.board)
            self._previous_foul_area = list(self.foul_area)
            self.status_var.set(self.t("calibration.confirm_previous"))
            self._render()
        else:
            self.reset_button.state(["disabled"])
            self.detect()

        self.window.after(40, self._poll_detection)

    def detect(self) -> None:
        self._detect_generation += 1
        generation = self._detect_generation
        self.progress.grid()
        self.progress.start(12)
        self.detect_button.state(["disabled"])
        self.preview_button.state(["disabled"])
        self.status_var.set(self.t("calibration.detecting"))
        frame, roi = self.frame.copy(), self.roi

        def worker() -> None:
            try:
                board = detect_board_corners(frame, roi)
                foul = detect_foul_line(frame, board) if board is not None else None
                payload: object = (board, foul)
            except (ValueError, cv2.error) as error:
                payload = error
            self._detect_queue.put((generation, payload))

        Thread(target=worker, name="startup-board-calibration", daemon=True).start()

    def _poll_detection(self) -> None:
        if self._closed:
            return
        try:
            while True:
                generation, payload = self._detect_queue.get_nowait()
                if generation != self._detect_generation:
                    continue
                self.progress.stop(); self.progress.grid_remove()
                self.detect_button.state(["!disabled"]); self.preview_button.state(["!disabled"])
                if isinstance(payload, Exception):
                    self._safe_guess()
                    self.status_var.set(self.t("calibration.board_not_found"))
                    self._render()
                    continue
                board, foul = payload
                if board is None:
                    self._safe_guess()
                    self.status_var.set(self.t("calibration.board_not_found"))
                else:
                    self.board = [tuple(map(float, point)) for point in board]
                    if foul is None:
                        self._guess_foul_band()
                        self.status_var.set(self.t("calibration.foul_not_found"))
                    else:
                        normalized = foul_band_from_line(foul, self.frame_size)
                        scale = np.asarray(self.frame_size, np.float32)
                        self.foul_area = [tuple(map(float, point)) for point in np.asarray(normalized, np.float32) * scale]
                        self.status_var.set(self.t("calibration.adjust_points"))
                self._render()
        except Empty:
            pass
        self.window.after(40, self._poll_detection)

    def _safe_guess(self) -> None:
        width, height = self.frame_size
        x, y, rw, rh = self.roi
        x0, y0, x1, y1 = x * width, y * height, (x + rw) * width, (y + rh) * height
        self.board = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        self._guess_foul_band()

    def _guess_foul_band(self) -> None:
        if len(self.board) != 4:
            return
        points = np.asarray(self.board, np.float32)
        first = points[0] * .5 + points[3] * .5
        second = points[1] * .5 + points[2] * .5
        normalized = foul_band_from_line((first, second), self.frame_size)
        scale = np.asarray(self.frame_size, np.float32)
        self.foul_area = [tuple(map(float, point)) for point in np.asarray(normalized, np.float32) * scale]

    def reset_previous(self) -> None:
        if self._previous_board and self._previous_foul_area:
            self.board = list(self._previous_board)
            self.foul_area = list(self._previous_foul_area)
            self.status_var.set(self.t("calibration.confirm_previous"))
            self._render()

    def use_current_frame(self) -> None:
        """Replace the startup snapshot with the latest live camera frame."""
        if self.current_frame_provider is None:
            return
        try:
            frame = self.current_frame_provider()
        except Exception:
            frame = None
        if frame is None or frame.ndim != 3 or frame.size == 0:
            self.status_var.set(self.t("calibration.current_frame_unavailable"))
            return

        old_width, old_height = self.frame_size
        new_height, new_width = frame.shape[:2]
        old_scale = np.asarray([max(1, old_width), max(1, old_height)], np.float32)
        new_scale = np.asarray([new_width, new_height], np.float32)

        def rescale(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
            if not points:
                return []
            values = np.asarray(points, np.float32) / old_scale * new_scale
            return [tuple(map(float, point)) for point in values]

        # Invalidate any detection still running against the previous frame.
        self._detect_generation += 1
        self.progress.stop(); self.progress.grid_remove()
        self.detect_button.state(["!disabled"]); self.preview_button.state(["!disabled"])
        self.board = rescale(self.board)
        self.foul_area = rescale(self.foul_area)
        self._previous_board = rescale(self._previous_board)
        self._previous_foul_area = rescale(self._previous_foul_area)
        self.frame = frame.copy()
        self.frame_size = (new_width, new_height)
        self.status_var.set(self.t("calibration.current_frame_replaced"))
        self._render()

    def _frame_to_canvas(self, point: Sequence[float]) -> tuple[float, float]:
        left, top, right, bottom = self._bounds
        return left + float(point[0]) / self.frame_size[0] * (right - left), top + float(point[1]) / self.frame_size[1] * (bottom - top)

    def _canvas_to_frame(self, x: float, y: float) -> tuple[float, float] | None:
        left, top, right, bottom = self._bounds
        if not (left <= x <= right and top <= y <= bottom):
            return None
        return ((x - left) / max(1.0, right - left) * self.frame_size[0], (y - top) / max(1.0, bottom - top) * self.frame_size[1])

    def _render(self, preview: bool = False) -> None:
        if self._closed:
            return
        self.canvas.delete("all")
        cw, ch = max(300, self.canvas.winfo_width()), max(220, self.canvas.winfo_height())
        scale = min((cw - 16) / self.frame_size[0], (ch - 16) / self.frame_size[1])
        rw, rh = max(1, int(self.frame_size[0] * scale)), max(1, int(self.frame_size[1] * scale))
        left, top = (cw - rw) / 2, (ch - rh) / 2
        shown = cv2.resize(self.frame, (rw, rh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        self._photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)))
        self.canvas.create_image(left, top, image=self._photo, anchor="nw")
        self._bounds = (left, top, left + rw, top + rh)
        for layer, points, colour in (("board", self.board, "#f5bd4f"), ("foul", self.foul_area, "#ff6675")):
            if len(points) != 4:
                continue
            coords = [value for point in points for value in self._frame_to_canvas(point)]
            self.canvas.create_polygon(*coords, outline=colour, fill="", width=1 if preview else 2)
            if not preview:
                for index, point in enumerate(points):
                    x, y = self._frame_to_canvas(point)
                    self.canvas.create_oval(x - 6, y - 6, x + 6, y + 6, fill=colour, outline="#111722", width=1)
                    self.canvas.create_text(x + 9, y - 8, text=str(index + 1), fill=colour, anchor="sw")

    def _press(self, event) -> str:
        point = self._canvas_to_frame(event.x, event.y)
        if point is None:
            return "break"
        nearest: tuple[float, str, int] | None = None
        for layer, points in (("board", self.board), ("foul", self.foul_area)):
            for index, existing in enumerate(points):
                distance = float(np.linalg.norm(np.asarray(existing) - np.asarray(point)))
                candidate = (distance, layer, index)
                if nearest is None or candidate < nearest:
                    nearest = candidate
        if nearest is not None and nearest[0] <= max(18.0, self.frame_size[0] * .025):
            self._drag_layer, self._drag_index = nearest[1], nearest[2]
        return "break"

    def _drag(self, event) -> str:
        if self._drag_index is None:
            return "break"
        point = self._canvas_to_frame(event.x, event.y)
        if point is None:
            return "break"
        points = self.board if self._drag_layer == "board" else self.foul_area
        points[self._drag_index] = point
        self._render()
        return "break"

    def _release(self, _event) -> str:
        self._drag_layer, self._drag_index = "", None
        return "break"

    def preview(self) -> None:
        if len(self.board) != 4 or len(self.foul_area) != 4:
            return
        self.detect_button.pack_forget(); self.current_frame_button.pack_forget(); self.reset_button.pack_forget(); self.preview_button.pack_forget(); self.skip_button.pack_forget()
        self.confirm_button.pack(side="left", padx=(0, 6)); self.back_button.pack(side="left")
        self.status_var.set(self.t("calibration.preview_help"))
        self._render(preview=True)

    def edit(self) -> None:
        self.back_button.pack_forget(); self.confirm_button.pack_forget()
        self.detect_button.pack(side="left", padx=(0, 6)); self.current_frame_button.pack(side="left", padx=(0, 6)); self.reset_button.pack(side="left", padx=(0, 6)); self.preview_button.pack(side="left", padx=(0, 6)); self.skip_button.pack(side="left")
        self.status_var.set(self.t("calibration.adjust_points"))
        self._render()

    def confirm(self) -> None:
        try:
            foul_line = foul_line_from_band(np.asarray(self.foul_area, np.float32) / np.asarray(self.frame_size, np.float32), self.frame_size)
            calibration = create_projection_calibration(self.board, foul_line, self.frame_size, self.camera_signature, self.previous)
        except (ValueError, cv2.error):
            self.status_var.set(self.t("calibration.invalid"))
            self.edit()
            return
        normalized_band = np.asarray(self.foul_area, np.float32) / np.asarray(self.frame_size, np.float32)
        self.on_confirm(calibration, tuple((float(x), float(y)) for x, y in normalized_band))
        self.close()

    def skip(self) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._detect_generation += 1
        self.progress.stop()
        try:
            self.window.destroy()
        finally:
            self.on_close()
