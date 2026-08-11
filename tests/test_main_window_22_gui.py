from __future__ import annotations

import time
import tkinter as tk

from src.config import AppConfig, save_config
from src.main_window import MainWindow
from src.models import AttemptDecision


def test_decision_saves_evidence_and_advances_roster(tmp_path):
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
    config.competition.auto_return_live = False
    config.shuttle.enabled = False
    config.display.window_geometry = "1050x680"
    path = tmp_path / "config.json"
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    root.after(550, app.toggle_freeze)
    root.after(950, lambda: app.mark_decision(AttemptDecision.VALID))
    root.after(1150, app.return_live)

    def inspect():
        attempts = app.attempts.attempts()
        result["attempt"] = attempts[0]
        result["current"] = app.competition.current_competitor()
        result["evidence"] = list((tmp_path / "exports" / "evidence").glob("*.png"))
        app.close()

    root.after(1650, inspect)
    root.after(6500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert result["attempt"].decision is AttemptDecision.VALID
    assert result["attempt"].competitor_number == 1
    assert result["current"] == 2
    assert len(result["evidence"]) >= 2


def test_clear_all_recordings_keeps_capture_running(tmp_path, monkeypatch):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .2, .2
    config.competition.enabled = False
    config.shuttle.enabled = False
    config.display.window_geometry = "1050x680"
    path = tmp_path / "config.json"; save_config(config, path)
    root = tk.Tk(); app = MainWindow(root, config, path); result = {}
    monkeypatch.setattr(app, "_ask_clear_recordings_mode", lambda: "all")
    root.after(500, app.toggle_freeze)
    def clear():
        app.clear_all_recordings()
        result["attempts"] = len(app.attempts.attempts())
        result["buffer_after"] = len(app.buffer)

    refill_deadline = time.monotonic() + 4.0
    def inspect():
        result["capture"] = app.capture.is_running
        result["buffer_refilled"] = len(app.buffer)
        if result["buffer_refilled"] == 0 and time.monotonic() < refill_deadline:
            root.after(100, inspect)
            return
        app.close()
    root.after(850, clear); root.after(1250, inspect)
    root.after(9000, lambda: root.destroy() if root.winfo_exists() else None); root.mainloop()
    assert result["attempts"] == 0
    assert result["capture"] is True
    assert result["buffer_refilled"] > result["buffer_after"]
