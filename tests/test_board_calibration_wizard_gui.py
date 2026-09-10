import tkinter as tk

import numpy as np

from src.board_calibration_wizard import BoardCalibrationWizard
from src.theme import DARK, ThemeManager
from src.top_view_projection import ProjectionCalibration


def test_saved_calibration_must_be_previewed_before_confirmation():
    root = tk.Tk()
    ThemeManager(root).apply("dark")
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    previous = ProjectionCalibration(
        ((.2, .2), (.8, .2), (.8, .8), (.2, .8)),
        ((.45, .2), (.45, .8)),
        "synthetic",
        320,
        180,
    )
    confirmed = []
    closed = []
    wizard = BoardCalibrationWizard(
        root,
        DARK,
        "en",
        frame,
        (.2, .2, .6, .6),
        "synthetic",
        previous,
        (),
        lambda calibration, area: confirmed.append((calibration, area)),
        lambda: closed.append(True),
    )
    root.update()
    assert wizard.confirm_button.winfo_manager() == ""
    assert len(wizard.board) == 4
    assert len(wizard.foul_area) == 4
    wizard.preview()
    root.update()
    assert wizard.confirm_button.winfo_manager() == "pack"
    wizard.confirm()
    root.update()
    assert len(confirmed) == 1
    assert len(confirmed[0][1]) == 4
    assert closed == [True]
    root.destroy()


def test_calibration_editor_can_be_skipped_without_saving():
    root = tk.Tk()
    ThemeManager(root).apply("dark")
    frame = np.zeros((120, 200, 3), dtype=np.uint8)
    previous = ProjectionCalibration(((.1, .1), (.9, .1), (.9, .9), (.1, .9)), ((.5, .1), (.5, .9)))
    confirmed = []
    wizard = BoardCalibrationWizard(
        root, DARK, "en", frame, (.1, .1, .8, .8), "camera", previous, (),
        lambda *_args: confirmed.append(True), lambda: None,
    )
    wizard.skip()
    root.update()
    assert confirmed == []
    root.destroy()


def test_calibration_editor_can_replace_startup_snapshot_with_current_camera_frame():
    root = tk.Tk()
    ThemeManager(root).apply("dark")
    initial = np.zeros((120, 200, 3), dtype=np.uint8)
    current = np.full((240, 400, 3), 175, dtype=np.uint8)
    previous = ProjectionCalibration(((.1, .2), (.9, .2), (.9, .8), (.1, .8)), ((.5, .2), (.5, .8)))
    wizard = BoardCalibrationWizard(
        root, DARK, "en", initial, (.1, .1, .8, .8), "camera", previous, (),
        lambda *_args: None, lambda: None, lambda: current,
    )
    original_board = np.asarray(wizard.board, np.float32)

    wizard.use_current_frame()
    root.update()

    assert wizard.frame_size == (400, 240)
    assert int(wizard.frame[0, 0, 0]) == 175
    assert np.allclose(np.asarray(wizard.board), original_board * 2)
    assert "current camera frame" in wizard.status_var.get()
    wizard.skip()
    root.destroy()
