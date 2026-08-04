from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from src.config import AppConfig, save_config
from src.main_window import MainWindow
from src.models import AttemptDecision


def _config(tmp_path) -> tuple[AppConfig, object]:
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .2, .1
    config.attempts.cache_directory = "cache"
    config.export.directory = "exports"
    config.competition.enabled = True
    config.competition.boys_competitors = 2
    config.competition.girls_enabled = False
    config.competition.default_attempts_per_competitor = 2
    config.competition.require_decision_before_continue = False
    config.competition.auto_advance_on_attempt_complete = True
    config.shuttle.enabled = False
    config.display.window_geometry = "1050x680"
    path = tmp_path / "config.json"
    save_config(config, path)
    return config, path


def test_not_decided_attempt_does_not_block_next_freeze(tmp_path):
    config, path = _config(tmp_path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    root.after(450, app.toggle_freeze)
    root.after(820, app.toggle_freeze)  # same Space action: return Live

    def second_freeze():
        result["athlete_after_first"] = app.competition.current_competitor()
        app.toggle_freeze()

    def inspect():
        attempts = app.attempts.attempts()
        result["attempts"] = attempts
        result["current_attempt"] = app.playback.attempt_id
        app.close()

    root.after(1050, second_freeze)
    root.after(1450, inspect)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result["athlete_after_first"] == 2
    assert len(result["attempts"]) == 2
    assert result["attempts"][0].decision is AttemptDecision.NOT_DECIDED
    assert result["attempts"][0].rotation_completed is True
    assert result["attempts"][1].competitor_number == 2
    assert result["current_attempt"] == result["attempts"][1].attempt_id


def test_freeze_projects_next_athlete_cell_before_live_rotation(tmp_path):
    config, path = _config(tmp_path)
    root = tk.Tk(); app = MainWindow(root, config, path); result = {}

    root.after(450, app.toggle_freeze)

    def inspect_frozen():
        projection = app._board_next_assignment
        result["projection"] = (projection.competitor_number, projection.attempt_number) if projection else None
        result["board_cell"] = (app.competition_board._active_athlete, app.competition_board._active_attempt)
        app.return_live()

    def inspect_live():
        result["current_athlete"] = app.competition.current_competitor()
        result["projection_after_live"] = app._board_next_assignment
        app.close()

    root.after(850, inspect_frozen)
    root.after(1100, inspect_live)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result["projection"] == (2, 1)
    assert result["board_cell"] == (2, 1)
    assert result["current_athlete"] == 2
    assert result["projection_after_live"] is None


def test_strict_decision_mode_can_still_block_return_live(tmp_path):
    config, path = _config(tmp_path)
    config.competition.require_decision_before_continue = True
    save_config(config, path)
    root = tk.Tk(); app = MainWindow(root, config, path); result = {}
    root.after(450, app.toggle_freeze)
    root.after(800, app.return_live)

    def inspect():
        result["attempt_id"] = app.playback.attempt_id
        result["athlete"] = app.competition.current_competitor()
        app.close()

    root.after(1100, inspect)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert result["attempt_id"] is not None
    assert result["athlete"] == 1


def test_deleting_undecided_attempt_in_strict_mode_leaves_consistent_live_state(tmp_path, monkeypatch):
    config, path = _config(tmp_path)
    config.competition.require_decision_before_continue = True
    save_config(config, path)
    monkeypatch.setattr(messagebox, "askyesno", lambda *args, **kwargs: True)
    root = tk.Tk(); app = MainWindow(root, config, path); result = {}
    root.after(450, app.toggle_freeze)
    root.after(850, app.delete_current_attempt)

    def inspect():
        result["attempts"] = app.attempts.attempts()
        result["mode"] = app.playback.mode
        result["attempt_id"] = app.playback.attempt_id
        result["athlete"] = app.competition.current_competitor()
        app.close()

    root.after(1100, inspect)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert result["attempts"] == []
    assert result["mode"].value == "LIVE"
    assert result["attempt_id"] is None
    assert result["athlete"] == 1


def test_judge_only_mode_hides_competition_board(tmp_path):
    config, path = _config(tmp_path)
    config.competition.enabled = False
    save_config(config, path)
    root = tk.Tk(); app = MainWindow(root, config, path)
    try:
        root.update_idletasks()
        assert not hasattr(app, "group_combo")
        assert not hasattr(app, "prev_athlete_button")
        assert not app.board_navigation.winfo_manager()
        assert app.side_notebook.tab(app.board_tab, "state") == "hidden"
    finally:
        app.close(); root.mainloop()

def test_header_menu_is_static_and_throttles_expensive_redraws(tmp_path):
    config, path = _config(tmp_path)
    config.performance.menu_throttle_enabled = True
    root = tk.Tk(); app = MainWindow(root, config, path)
    try:
        root.update_idletasks()
        menu_id = str(app.file_menu)
        normal_hz = app._effective_preview_hz()
        app._begin_menu_interaction()
        throttled_hz = app._effective_preview_hz()
        for _ in range(5):
            app._tick(); root.update_idletasks()
        assert str(app.file_menu) == menu_id
        assert str(app.file_menu.cget("background")) == app.palette["surface"]
        assert str(app.file_menu.cget("activebackground")) == app.palette["selection"]
        assert "Segoe UI" in str(app.file_menu.cget("font"))
        app.config.display.theme = "light"; app._apply_theme()
        assert str(app.file_menu.cget("background")) == app.palette["surface"]
        assert str(app.file_menu.cget("activebackground")) == app.palette["selection"]
        assert throttled_hz <= 15
        assert throttled_hz <= normal_hz
    finally:
        app.close(); root.mainloop()


def test_near_screen_geometry_is_maximized_instead_of_borderless_floating():
    assert MainWindow._geometry_nearly_fills_screen("1920x1009+0+0", 1920, 1080)
    assert not MainWindow._geometry_nearly_fills_screen("1360x820+100+80", 1920, 1080)
    assert not MainWindow._geometry_nearly_fills_screen("invalid", 1920, 1080)
