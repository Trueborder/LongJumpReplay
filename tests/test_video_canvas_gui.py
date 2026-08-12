import tkinter as tk

import cv2
import numpy as np

from src.theme import DARK
from src.video_canvas import VideoCanvas


def test_video_canvas_defers_render_during_window_interaction():
    root = tk.Tk()
    canvas = VideoCanvas(root, DARK)
    canvas.pack(fill="both", expand=True)
    root.update()

    canvas.set_render_suspended(True)
    for value in range(20):
        canvas.set_frame(np.full((90, 160, 3), value, dtype=np.uint8))
    assert canvas._dirty_while_suspended
    assert not canvas._render_pending

    canvas.set_render_suspended(False)
    root.update_idletasks()
    assert not canvas._dirty_while_suspended
    assert not canvas._render_pending
    root.destroy()


def test_video_canvas_reuses_render_items_for_frames():
    root = tk.Tk()
    canvas = VideoCanvas(root, DARK)
    canvas.pack(fill="both", expand=True)
    root.update()
    item_ids = canvas.find_all()

    for value in range(5):
        canvas.set_frame(np.full((90, 160, 3), value, dtype=np.uint8))
        root.update_idletasks()

    assert canvas.find_all() == item_ids
    root.destroy()


def test_video_canvas_zoom_renders_only_the_visible_viewport(monkeypatch):
    root = tk.Tk()
    root.geometry("640x360")
    canvas = VideoCanvas(root, DARK)
    canvas.pack(fill="both", expand=True)
    root.update()
    requested_sizes = []
    real_resize = cv2.resize

    def recording_resize(source, size, *args, **kwargs):
        requested_sizes.append(size)
        return real_resize(source, size, *args, **kwargs)

    monkeypatch.setattr("src.video_canvas.cv2.resize", recording_resize)
    canvas.zoom = 10.0
    canvas.set_frame(np.zeros((1080, 1920, 3), dtype=np.uint8))
    root.update_idletasks()

    assert requested_sizes
    width, height = requested_sizes[-1]
    assert width <= canvas.winfo_width() + 20
    assert height <= canvas.winfo_height() + 20
    assert width * height < 300_000
    root.destroy()
