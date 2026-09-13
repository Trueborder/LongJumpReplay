import tkinter as tk
from tkinter import ttk

from src.config import AppConfig, save_config
from src.main_window import MainWindow
from src.top_view_projection import TopViewProjectionWindow


def test_failed_shoe_detection_uses_neutral_unavailable_split_result():
    root = tk.Tk()
    root.withdraw()
    projection = TopViewProjectionWindow.__new__(TopViewProjectionWindow)
    projection.language = "en"
    projection._split_review_badge = tk.Label(root)
    projection._split_review_detail = tk.Label(root)
    projection._split_review_stage_var = tk.StringVar(root)
    projection._split_review_progress = ttk.Progressbar(root)
    projection._split_review_progress.pack()
    rendered = []
    projection._split_review_render = lambda: rendered.append(True)

    projection._update_split_review_unavailable("No reliable shoe outline was found.")

    assert projection._split_review_badge.cget("text") == "NOT AVAILABLE"
    assert projection._split_review_badge.cget("background") == "#69737d"
    assert projection._split_review_stage_var.get() == "Shoe detection failed."
    assert projection._split_review_progress.winfo_manager() == ""
    assert rendered == [True]
    root.destroy()


def test_dismissing_failed_fullscreen_review_returns_to_projection_menu():
    root = tk.Tk()
    root.withdraw()
    projection = TopViewProjectionWindow.__new__(TopViewProjectionWindow)
    projection._closed = False
    projection._state = "projection_unavailable"
    projection.window = tk.Toplevel(root)
    projection.selection_page = ttk.Frame(projection.window)
    projection.selection_page.grid(row=1, column=0)
    projection.workspace_page = ttk.Frame(projection.window)
    projection.workspace_page.grid(row=1, column=0)
    projection.manual_setup_button = ttk.Button(projection.selection_page)
    projection.confirm_frame_button = ttk.Button(projection.selection_page)
    projection.confirm_frame_button.pack(side="left")
    projection._analysis_failure = {"layer": "shoe", "message": "No shoe"}
    projection._split_review_window = tk.Toplevel(projection.window)
    projection._split_review_photos = []
    projection._split_review_render = None
    projection._split_review_progress = None
    projection._split_review_stage_var = None
    projection._split_review_badge = None
    projection._split_review_detail = None
    projection._split_review_reveal_image = None
    projection._split_review_animation_job = None
    projection._render_selection = lambda: None
    projection._text = lambda english, _czech: english
    projection._close_split_review()
    root.update_idletasks()

    assert projection._state == "selecting_frame"
    assert projection.selection_page.winfo_manager() == "grid"
    assert projection.workspace_page.winfo_manager() == ""
    assert projection.manual_setup_button.winfo_manager() == "pack"

    projection.window.destroy()
    root.destroy()


def test_top_down_projection_uses_current_frame_without_chooser(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .2, .1
    config.display.window_geometry = "1000x650"
    config.general.onboarding_completed = True
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
