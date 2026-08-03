import tkinter as tk

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
