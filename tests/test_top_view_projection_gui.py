import tkinter as tk

from src.config import AppConfig, save_config
from src.main_window import MainWindow


def test_top_down_projection_uses_current_frame_without_chooser(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .2, .1
    config.display.window_geometry = "1000x650"
    config.general.onboarding_completed = True
    config.general.recording_mode_prompted = True
    config.shuttle.enabled = False
    path = tmp_path / "config.json"
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    app._evaluation_mode = False
    app._trial_expired = False
    result = {}

    def freeze():
        app.toggle_freeze()

    def open_projection():
        app.open_top_view_projection()
        result["loading_visible"] = app._top_view_loading_dialog is not None
        result["split_immediate"] = bool(
            app._top_view_window is not None
            and app._top_view_window._split_review_window is not None
        )
        wait_for_window()

    def wait_for_window():
        projection = app._top_view_window
        if projection is None:
            root.after(50, wait_for_window)
            return
        result["opened"] = True
        result["title"] = projection.window.title()
        result["state"] = projection._state
        result["candidates"] = len(projection.candidates)
        result["selection_visible"] = projection.selection_page.winfo_manager() == "grid"
        result["one_projection"] = projection.overhead_canvas.master.winfo_manager() == "grid"
        result["board_hidden"] = projection.board_canvas.master.winfo_manager() != "grid"
        root.after(900, finish)

    def finish():
        if app._top_view_window is not None:
            app._top_view_window.close()
        app.close()

    root.after(1100, freeze)
    root.after(1800, open_projection)
    root.after(7000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result["loading_visible"] is False
    assert result["split_immediate"] is True
    assert result["opened"] is True
    assert result["title"] == "Top-down projection"
    assert result["candidates"] == 1
    assert result["selection_visible"] is False
    assert result["one_projection"] is True
    assert result["board_hidden"] is True
    assert not app.capture.is_running
