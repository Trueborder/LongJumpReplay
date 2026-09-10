from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable

import cv2
import numpy as np
from PIL import Image, ImageTk

from .i18n import tr
from .language_catalog import normalize_language


class VideoCanvas(tk.Canvas):
    """Video surface with zoom, pan and board calibration overlays.

    Guide angle is measured from vertical: 0° is the traditional vertical
    take-off plane, positive values rotate clockwise on screen.
    """

    def __init__(
        self,
        master,
        palette: dict[str, str],
        guide_enabled: bool = True,
        guide_x_ratio: float = .5,
        guide_y_ratio: float = .5,
        guide_angle_deg: float = 0.0,
        guide_width_px: int = 2,
        guide_changed: Callable[..., None] | None = None,
        board_roi: tuple[float, float, float, float] = (.35, .35, .30, .45),
        board_roi_enabled: bool = True,
        board_roi_visible: bool = False,
        projection_board: tuple[tuple[float, float], ...] = (),
        projection_foul_area: tuple[tuple[float, float], ...] = (),
        calibration_changed: Callable[[dict[str, float]], None] | None = None,
        compact: bool = False,
        language: str = "en",
        **kwargs,
    ) -> None:
        super().__init__(master, background=palette["video"], highlightthickness=1, highlightbackground=palette["border"], **kwargs)
        self.palette = palette
        self.language = normalize_language(language)
        self._frame: np.ndarray | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._status_text = tr(self.language, "overlay.waiting_video")
        self._status_color = palette["muted"]
        self._secondary_text = ""
        self.guide_enabled = guide_enabled
        self.guide_x_ratio = guide_x_ratio
        self.guide_y_ratio = guide_y_ratio
        self.guide_angle_deg = guide_angle_deg
        self.guide_width_px = max(1, min(20, int(guide_width_px)))
        self.guide_changed = guide_changed
        self.board_roi = tuple(board_roi)
        self.board_roi_enabled = board_roi_enabled
        self.board_roi_visible = board_roi_visible
        self.projection_board = tuple(tuple(map(float, point)) for point in projection_board)
        self.projection_foul_area = tuple(tuple(map(float, point)) for point in projection_foul_area)
        self.calibration_changed = calibration_changed
        self.calibration_mode = False
        self.compact = compact
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self._drag_start: tuple[int, int] | None = None
        self._drag_mode = ""
        self._roi_draw_start: tuple[float, float] | None = None
        self._image_bounds = (0.0, 0.0, 1.0, 1.0)
        self._render_pending = False
        self._render_suspended = False
        self._dirty_while_suspended = False
        self.bind("<Configure>", lambda _e: self.request_render())
        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._on_linux_wheel(e, 1))
        self.bind("<Button-5>", lambda e: self._on_linux_wheel(e, -1))
        self.bind("<ButtonPress-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_drag_end)
        self.bind("<Control-Button-1>", self._on_set_guide)
        self.bind("<Double-Button-1>", lambda _e: self.reset_view())

        # Keep the item graph stable while frames arrive.  Recreating every
        # item for each preview frame makes Tk allocate and discard many
        # objects at high refresh rates.
        self._image_item = self.create_image(0, 0, anchor="center", state="hidden")
        self._empty_item = self.create_text(0, 0, state="hidden")
        self._guide_line = self.create_line(0, 0, 0, 0, state="hidden")
        self._guide_center = self.create_oval(0, 0, 0, 0, state="hidden")
        self._guide_handle = self.create_oval(0, 0, 0, 0, state="hidden")
        self._guide_box = self.create_rectangle(0, 0, 0, 0, state="hidden")
        self._guide_label = self.create_text(0, 0, state="hidden")
        self._roi_box = self.create_rectangle(0, 0, 0, 0, state="hidden")
        self._roi_handle = self.create_rectangle(0, 0, 0, 0, state="hidden")
        self._roi_label = self.create_text(0, 0, state="hidden")
        self._projection_board_item = self.create_polygon(0, 0, 0, 0, state="hidden", fill="")
        self._projection_foul_item = self.create_polygon(0, 0, 0, 0, state="hidden", fill="")
        self._status_box = self.create_rectangle(0, 0, 0, 0)
        self._status_label = self.create_text(0, 0)
        self._help_label = self.create_text(0, 0, state="hidden")
        self._secondary_label = self.create_text(0, 0, state="hidden")

    def set_language(self, language: str) -> None:
        previous_waiting = tr(self.language, "overlay.waiting_video")
        self.language = normalize_language(language)
        if self._status_text == previous_waiting:
            self._status_text = tr(self.language, "overlay.waiting_video")
        self.request_render()

    def apply_palette(self, palette: dict[str, str]) -> None:
        self.palette = palette
        self.configure(background=palette["video"], highlightbackground=palette["border"])
        self.request_render()

    def set_frame(self, frame_bgr: np.ndarray | None) -> None:
        self._frame = frame_bgr
        self.request_render()

    def set_status(self, text: str, color: str | None = None, secondary: str = "") -> None:
        status_color = color or self.palette["muted"]
        if (text, status_color, secondary) == (self._status_text, self._status_color, self._secondary_text):
            return
        self._status_text = text
        self._status_color = status_color
        self._secondary_text = secondary
        self.request_render()

    def set_guide_enabled(self, enabled: bool) -> None:
        self.guide_enabled = enabled
        self.request_render()

    def set_calibration_mode(self, enabled: bool) -> None:
        self.calibration_mode = bool(enabled)
        if enabled:
            self.guide_enabled = True
            self.board_roi_visible = True
        self.configure(cursor="crosshair" if enabled else "")
        self.request_render()

    def set_calibration(
        self,
        guide_x: float,
        guide_y: float,
        angle_deg: float,
        roi: tuple[float, float, float, float],
        roi_enabled: bool,
        roi_visible: bool,
        guide_width_px: int | None = None,
    ) -> None:
        self.guide_x_ratio = max(0.0, min(1.0, guide_x))
        self.guide_y_ratio = max(0.0, min(1.0, guide_y))
        self.guide_angle_deg = max(-89.9, min(89.9, angle_deg))
        self.board_roi = self._clamp_roi(roi)
        self.board_roi_enabled = roi_enabled
        self.board_roi_visible = roi_visible
        if guide_width_px is not None:
            self.guide_width_px = max(1, min(20, int(guide_width_px)))
        self.request_render()

    def set_projection_overlay(
        self,
        board: tuple[tuple[float, float], ...],
        foul_area: tuple[tuple[float, float], ...],
    ) -> None:
        self.projection_board = tuple(tuple(map(float, point)) for point in board)
        self.projection_foul_area = tuple(tuple(map(float, point)) for point in foul_area)
        self.request_render()

    def reset_view(self) -> None:
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.request_render()

    def set_render_suspended(self, suspended: bool) -> None:
        if self._render_suspended == suspended:
            return
        self._render_suspended = suspended
        if not suspended and self._dirty_while_suspended:
            self._dirty_while_suspended = False
            self.request_render()

    def request_render(self) -> None:
        if self._render_suspended:
            self._dirty_while_suspended = True
            return
        if self._render_pending:
            return
        self._render_pending = True
        try:
            self.after_idle(self._render)
        except tk.TclError:
            self._render_pending = False

    def _render(self) -> None:
        self._render_pending = False
        if self._render_suspended:
            self._dirty_while_suspended = True
            return
        w, h = max(2, self.winfo_width()), max(2, self.winfo_height())
        for item in (
            self._empty_item,
            self._guide_line,
            self._guide_center,
            self._guide_handle,
            self._guide_box,
            self._guide_label,
            self._roi_box,
            self._roi_handle,
            self._roi_label,
            self._projection_board_item,
            self._projection_foul_item,
            self._help_label,
            self._secondary_label,
        ):
            self.itemconfigure(item, state="hidden")
        if self._frame is None:
            self.coords(self._empty_item, w / 2, h / 2)
            self.itemconfigure(self._empty_item, state="normal", text=tr(self.language, "overlay.no_video"), fill=self.palette["muted"], font=("Segoe UI Semibold", 13))
            self.itemconfigure(self._image_item, state="hidden")
            self._image_bounds = (0.0, 0.0, float(w), float(h))
            self._draw_overlay(w, h)
            return
        fh, fw = self._frame.shape[:2]
        fit = min(w / fw, h / fh)
        scale = max(.05, fit * self.zoom)
        dw, dh = max(1, round(fw * scale)), max(1, round(fh * scale))
        cx, cy = w / 2 + self.pan_x, h / 2 + self.pan_y
        left, top, right, bottom = cx - dw / 2, cy - dh / 2, cx + dw / 2, cy + dh / 2
        self._image_bounds = (left, top, right, bottom)
        visible_left, visible_top = max(0.0, left), max(0.0, top)
        visible_right, visible_bottom = min(float(w), right), min(float(h), bottom)
        if visible_right > visible_left and visible_bottom > visible_top:
            # Resize only the source pixels that can appear in the viewport.
            # Rendering the complete image at 10x zoom created tens of millions
            # of temporary pixels for Tk to clip away on every preview frame.
            sx0 = max(0, min(fw - 1, math.floor((visible_left - left) / scale)))
            sy0 = max(0, min(fh - 1, math.floor((visible_top - top) / scale)))
            sx1 = max(sx0 + 1, min(fw, math.ceil((visible_right - left) / scale)))
            sy1 = max(sy0 + 1, min(fh, math.ceil((visible_bottom - top) / scale)))
            source = self._frame[sy0:sy1, sx0:sx1]
            render_width = max(1, round((sx1 - sx0) * scale))
            render_height = max(1, round((sy1 - sy0) * scale))
            resized = cv2.resize(
                source,
                (render_width, render_height),
                interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
            )
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            self._photo = ImageTk.PhotoImage(Image.fromarray(rgb))
            render_cx = left + sx0 * scale + render_width / 2
            render_cy = top + sy0 * scale + render_height / 2
            self.coords(self._image_item, render_cx, render_cy)
            self.itemconfigure(self._image_item, state="normal", image=self._photo)
        else:
            self.itemconfigure(self._image_item, state="hidden")
        has_board_polygon = len(self.projection_board) == 4
        has_foul_polygon = len(self.projection_foul_area) == 4
        if self.board_roi_enabled and (self.board_roi_visible or self.calibration_mode) and not has_board_polygon:
            self._draw_roi(left, top, dw, dh)
        if self.guide_enabled and not has_foul_polygon:
            self._draw_guide(left, top, dw, dh)
        if has_board_polygon and self.board_roi_visible:
            self._draw_projection_polygon(self._projection_board_item, self.projection_board, left, top, dw, dh, self.palette["warning"])
        if has_foul_polygon and self.guide_enabled:
            self._draw_projection_polygon(self._projection_foul_item, self.projection_foul_area, left, top, dw, dh, self.palette["danger"])
        self._draw_overlay(w, h)

    def _draw_projection_polygon(self, item: int, points, left: float, top: float, dw: float, dh: float, colour: str) -> None:
        coords = [value for x, y in points for value in (left + x * dw, top + y * dh)]
        self.coords(item, *coords)
        self.itemconfigure(item, state="normal", outline=colour, fill="", width=1)

    def _draw_guide(self, left: float, top: float, dw: float, dh: float) -> None:
        gx = left + dw * self.guide_x_ratio
        gy = top + dh * self.guide_y_ratio
        angle = math.radians(self.guide_angle_deg)
        half = math.hypot(dw, dh)
        dx, dy = math.sin(angle) * half, math.cos(angle) * half
        self.coords(self._guide_line, gx - dx, gy - dy, gx + dx, gy + dy)
        self.itemconfigure(self._guide_line, state="normal", fill=self.palette["danger"], width=self.guide_width_px)
        if not self.compact:
            self.coords(self._guide_center, gx - 4, gy - 4, gx + 4, gy + 4)
            self.itemconfigure(self._guide_center, state="normal", fill=self.palette["danger"], outline="")
            hx, hy = gx + math.sin(angle) * 54, gy - math.cos(angle) * 54
            if self.calibration_mode:
                self.coords(self._guide_handle, hx - 6, hy - 6, hx + 6, hy + 6)
                self.itemconfigure(self._guide_handle, state="normal", fill=self.palette["warning"], outline=self.palette["surface"])
            board_label = tr(self.language, "overlay.board")
            label = f"{board_label}  {self.guide_angle_deg:+.1f}°" if self.calibration_mode else board_label
            self.coords(self._guide_box, gx - 42, max(top + 8, 8), gx + 42, max(top + 27, 27))
            self.itemconfigure(self._guide_box, state="normal", fill=self.palette["surface"], outline=self.palette["danger"])
            self.coords(self._guide_label, gx, max(top + 17, 17))
            self.itemconfigure(self._guide_label, state="normal", text=label, fill=self.palette["danger"], font=("Segoe UI Semibold", 7))

    def _draw_roi(self, left: float, top: float, dw: float, dh: float) -> None:
        x, y, rw, rh = self.board_roi
        x0, y0 = left + x * dw, top + y * dh
        x1, y1 = x0 + rw * dw, y0 + rh * dh
        self.coords(self._roi_box, x0, y0, x1, y1)
        self.itemconfigure(self._roi_box, state="normal", outline=self.palette["warning"], width=2, dash=(6, 4))
        if self.calibration_mode:
            self.coords(self._roi_handle, x1 - 7, y1 - 7, x1 + 7, y1 + 7)
            self.itemconfigure(self._roi_handle, state="normal", fill=self.palette["warning"], outline=self.palette["surface"])
            self.coords(self._roi_label, x0 + 6, y0 + 5)
            self.itemconfigure(self._roi_label, state="normal", anchor="nw", text=tr(self.language, "overlay.takeoff_roi"), fill=self.palette["warning"], font=("Segoe UI Semibold", 8))

    def _draw_overlay(self, w: int, h: int) -> None:
        pad = 8 if self.compact else 10
        font_size = 8 if self.compact else 9
        self.coords(self._status_box, pad, pad, min(w - pad, 500), pad + (24 if self.compact else 28))
        self.itemconfigure(self._status_box, fill=self.palette["surface"], outline=self.palette["border"])
        self.coords(self._status_label, pad + 9, pad + (12 if self.compact else 14))
        self.itemconfigure(self._status_label, anchor="w", text=self._status_text, fill=self._status_color, font=("Segoe UI Semibold", font_size))
        if self.calibration_mode and not self.compact:
            self.coords(self._help_label, 12, h - 12)
            self.itemconfigure(self._help_label, state="normal", anchor="sw", text=tr(self.language, "overlay.calibration_help"), fill=self.palette["warning"], font=("Segoe UI", 8))
        elif self._secondary_text and not self.compact:
            self.coords(self._secondary_label, w - 10, h - 9)
            self.itemconfigure(self._secondary_label, state="normal", anchor="se", text=self._secondary_text, fill=self.palette["muted"], font=("Segoe UI", 8))

    def _canvas_to_ratio(self, x: float, y: float) -> tuple[float, float]:
        left, top, right, bottom = self._image_bounds
        return (
            max(0.0, min(1.0, (x - left) / max(1.0, right - left))),
            max(0.0, min(1.0, (y - top) / max(1.0, bottom - top))),
        )

    def _ratio_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        left, top, right, bottom = self._image_bounds
        return left + x * (right - left), top + y * (bottom - top)

    def _notify_calibration(self) -> None:
        if self.guide_changed:
            try:
                self.guide_changed(self.guide_x_ratio, self.guide_y_ratio, self.guide_angle_deg)
            except TypeError:
                self.guide_changed(self.guide_x_ratio)
        if self.calibration_changed:
            x, y, w, h = self.board_roi
            self.calibration_changed({
                "guide_x_ratio": self.guide_x_ratio,
                "guide_y_ratio": self.guide_y_ratio,
                "guide_angle_deg": self.guide_angle_deg,
                "board_roi_x": x,
                "board_roi_y": y,
                "board_roi_width": w,
                "board_roi_height": h,
            })

    def _zoom_at(self, x: int, y: int, factor: float) -> None:
        old = self.zoom
        new = max(1.0, min(10.0, old * factor))
        if abs(new - old) < 1e-9:
            return
        cx, cy = self.winfo_width() / 2, self.winfo_height() / 2
        ratio = new / old
        self.pan_x = (x - cx) - ((x - cx) - self.pan_x) * ratio
        self.pan_y = (y - cy) - ((y - cy) - self.pan_y) * ratio
        self.zoom = new
        self.request_render()

    def _on_wheel(self, event) -> str:
        if event.state & 0x0004:
            self.guide_angle_deg = max(-89.9, min(89.9, self.guide_angle_deg + (0.5 if event.delta > 0 else -0.5)))
            self._notify_calibration(); self.request_render()
            return "break"
        self._zoom_at(event.x, event.y, 1.15 if event.delta > 0 else 1 / 1.15)
        return "break"

    def _on_linux_wheel(self, event, direction: int) -> str:
        if event.state & 0x0004:
            self.guide_angle_deg = max(-89.9, min(89.9, self.guide_angle_deg + (0.5 if direction > 0 else -0.5)))
            self._notify_calibration(); self.request_render(); return "break"
        self._zoom_at(event.x, event.y, 1.15 if direction > 0 else 1 / 1.15)
        return "break"

    def _on_drag_start(self, event) -> str | None:
        if event.state & 0x0004:
            return self._on_set_guide(event)
        if self.calibration_mode:
            rx, ry = self._canvas_to_ratio(event.x, event.y)
            if event.state & 0x0001:  # Shift
                self._drag_mode = "draw_roi"
                self._roi_draw_start = (rx, ry)
                self.board_roi = (rx, ry, .001, .001)
            else:
                cx, cy = self._ratio_to_canvas(self.guide_x_ratio, self.guide_y_ratio)
                angle = math.radians(self.guide_angle_deg)
                hx, hy = cx + math.sin(angle) * 54, cy - math.cos(angle) * 54
                x, y, w, h = self.board_roi
                x1, y1 = self._ratio_to_canvas(x + w, y + h)
                if math.hypot(event.x - hx, event.y - hy) <= 16:
                    self._drag_mode = "rotate_guide"
                elif math.hypot(event.x - x1, event.y - y1) <= 18:
                    self._drag_mode = "resize_roi"
                elif x <= rx <= x + w and y <= ry <= y + h:
                    self._drag_mode = "move_roi"
                    self._drag_start = (event.x, event.y)
                else:
                    self._drag_mode = "move_guide"
                    self.guide_x_ratio, self.guide_y_ratio = rx, ry
            self._notify_calibration(); self.request_render()
            return "break"
        self._drag_mode = "pan"
        self._drag_start = (event.x, event.y)
        return None

    def _on_drag(self, event) -> str | None:
        if self._drag_mode == "pan" and self._drag_start:
            x, y = self._drag_start
            self.pan_x += event.x - x; self.pan_y += event.y - y
            self._drag_start = (event.x, event.y)
        elif self.calibration_mode:
            rx, ry = self._canvas_to_ratio(event.x, event.y)
            if self._drag_mode == "move_guide":
                self.guide_x_ratio, self.guide_y_ratio = rx, ry
            elif self._drag_mode == "rotate_guide":
                cx, cy = self._ratio_to_canvas(self.guide_x_ratio, self.guide_y_ratio)
                self.guide_angle_deg = max(-89.9, min(89.9, math.degrees(math.atan2(event.x - cx, cy - event.y))))
            elif self._drag_mode == "draw_roi" and self._roi_draw_start:
                sx, sy = self._roi_draw_start
                self.board_roi = self._clamp_roi((min(sx, rx), min(sy, ry), abs(rx - sx), abs(ry - sy)))
            elif self._drag_mode == "resize_roi":
                x, y, _w, _h = self.board_roi
                self.board_roi = self._clamp_roi((x, y, max(.01, rx - x), max(.01, ry - y)))
            elif self._drag_mode == "move_roi" and self._drag_start:
                old_rx, old_ry = self._canvas_to_ratio(*self._drag_start)
                x, y, w, h = self.board_roi
                self.board_roi = self._clamp_roi((x + rx - old_rx, y + ry - old_ry, w, h))
                self._drag_start = (event.x, event.y)
            self._notify_calibration()
        self.request_render()
        return "break" if self.calibration_mode else None

    def _on_drag_end(self, _event) -> None:
        self._drag_start = None
        self._roi_draw_start = None
        self._drag_mode = ""

    def _on_set_guide(self, event) -> str:
        self.guide_x_ratio, self.guide_y_ratio = self._canvas_to_ratio(event.x, event.y)
        self.guide_enabled = True
        self._notify_calibration()
        self.request_render()
        return "break"

    @staticmethod
    def _clamp_roi(roi: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        x, y, w, h = roi
        w = max(.01, min(1.0, w)); h = max(.01, min(1.0, h))
        x = max(0.0, min(1.0 - w, x)); y = max(0.0, min(1.0 - h, y))
        return x, y, w, h
