from __future__ import annotations

import tkinter as tk

from src.athlete_timer import AthleteTimerState
from src.config import AppConfig, save_config
from src.main_window import MainWindow


def test_system_pause_stops_camera_clears_live_buffer_and_resumes(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.cache_directory = "cache"
    config.shuttle.enabled = False
    config.display.window_geometry = "1050x680"
    config.display.window_maximized = False
    path = tmp_path / "config.json"
    save_config(config, path)

    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    root.after(450, app.toggle_system_pause)

    def inspect_paused():
        result["paused"] = app._system_paused
        result["stopped"] = not app.capture.is_running
        result["buffer_empty"] = len(app.buffer) == 0
        result["latest_empty"] = app.capture.latest.get()[0] is None
        app.toggle_freeze()
        app.toggle_athlete_timer()
        result["attempts"] = app.attempts.attempts()
        result["timer"] = app.athlete_timer.state
        app.toggle_system_pause()

    def inspect_resumed():
        result["resumed"] = not app._system_paused and app.capture.is_running
        result["frames_after_resume"] = len(app.buffer)
        app.close()

    root.after(1050, inspect_paused)
    root.after(1650, inspect_resumed)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result["paused"] is True
    assert result["stopped"] is True
    assert result["buffer_empty"] is True
    assert result["latest_empty"] is True
    assert result["attempts"] == []
    assert result["timer"] is AthleteTimerState.READY
    assert result["resumed"] is True
    assert result["frames_after_resume"] > 0
