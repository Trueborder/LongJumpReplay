import tkinter as tk

from src.theme import DARK
from src.video_canvas import VideoCanvas


def test_rotated_guide_and_roi_configuration_round_trip():
    root = tk.Tk(); changes = []
    canvas = VideoCanvas(root, DARK, calibration_changed=changes.append)
    canvas.pack(); root.update()
    canvas.set_calibration(.42, .61, 17.5, (.2, .3, .4, .25), True, True)
    assert canvas.guide_x_ratio == .42
    assert canvas.guide_y_ratio == .61
    assert canvas.guide_angle_deg == 17.5
    assert canvas.board_roi == (.2, .3, .4, .25)
    canvas.set_calibration_mode(True)
    assert canvas.calibration_mode
    assert canvas.board_roi_visible
    root.destroy()
