from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch
import tkinter as tk

from src.athlete_timer import AthleteTimerController, AthleteTimerState
from src.config import AppConfig, save_config
from src.i18n import tr
from src.main_window import MainWindow
from src.playback import PlaybackMode


class FakeClock:
    def __init__(self) -> None:
        self.now_ns = 0

    def __call__(self) -> int:
        return self.now_ns


def _config(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .2, .1
    config.attempts.cache_directory = "cache"
    config.export.directory = "exports"
    config.competition.boys_competitors = 2
    config.competition.girls_enabled = False
    config.shuttle.enabled = False
    config.hotkeys.bindings["timer_toggle"] = "F2"
    config.display.window_geometry = "1050x680"
    path = tmp_path / "config.json"
    save_config(config, path)
    return config, path


def test_athlete_timer_gui_workflow_and_rendering(tmp_path):
    config, path = _config(tmp_path)
    root = tk.Tk(); app = MainWindow(root, config, path); messages = []
    app._show_message = lambda message, _seconds=0: messages.append(message)
    try:
        # Click and hotkey use the same start/stop action.
        root.update()
        app.timer_value_label.event_generate("<Button-1>", x=2, y=2); root.update()
        assert app.athlete_timer.state is AthleteTimerState.RUNNING
        app.timer_value_label.focus_force(); root.update()
        root.event_generate("<KeyPress-F2>"); root.update()
        root.event_generate("<KeyRelease-F2>"); root.update()
        assert app.athlete_timer.state is AthleteTimerState.STOPPED

        # Starts are Live-only, and a failed Freeze does not stop a run.
        app.playback.mode = PlaybackMode.LIVE_BUFFER
        app.toggle_athlete_timer()
        assert app.athlete_timer.state is AthleteTimerState.STOPPED
        assert messages[-1] == tr("en", "timer.live_only")
        app.playback.mode = PlaybackMode.LIVE
        app.toggle_athlete_timer()
        with patch.object(type(app.playback), "freeze_to_new_attempt", return_value=None):
            app.toggle_freeze()
        assert app.athlete_timer.state is AthleteTimerState.RUNNING
        with patch.object(type(app.playback), "freeze_to_new_attempt", return_value=42):
            app.toggle_freeze()
        assert app.athlete_timer.state is AthleteTimerState.STOPPED

        # Replay-to-Live, manual athlete changes, and duration Apply reset READY.
        app.playback.mode = PlaybackMode.LIVE_BUFFER
        app._clear_recordings_mode("live", ask=False)
        assert app.athlete_timer.state is AthleteTimerState.READY
        app.athlete_timer.start(); app._select_competitor_delta(1)
        assert app.athlete_timer.state is AthleteTimerState.READY
        updated = deepcopy(app.config)
        updated.athlete_timer.duration_seconds = 75
        app.athlete_timer.start(); app.apply_settings(updated)
        assert app.athlete_timer.state is AthleteTimerState.READY
        assert app.timer_value_var.get() == "01:15"

        # Only READY blinks; running warnings and expiry use theme colors.
        clock = FakeClock(); app.athlete_timer = AthleteTimerController(60, clock)
        with patch("src.main_window.time.monotonic", return_value=0.0):
            app._update_athlete_timer_display(); ready_on = app.timer_prefix_label.cget("fg")
        value_color = app.timer_value_label.cget("fg")
        with patch("src.main_window.time.monotonic", return_value=0.5):
            app._update_athlete_timer_display(); ready_off = app.timer_prefix_label.cget("fg")
        assert ready_on != ready_off
        assert app.timer_value_label.cget("fg") == value_color
        app.athlete_timer.start(); clock.now_ns = 50_000_000_000
        app._update_athlete_timer_display()
        assert app.timer_value_label.cget("fg") == app.palette["warning"]
        clock.now_ns = 60_000_000_000
        app._update_athlete_timer_display()
        assert app.timer_value_var.get() == "00:00"
        assert app.timer_value_label.cget("fg") == app.palette["danger"]

        # The timer stays farthest right and readable in both themes.
        for theme in ("light", "dark"):
            app.config.display.theme = theme; app._apply_theme(); root.update_idletasks()
            assert app.timer_frame.winfo_rootx() > app.mode_badge.winfo_rootx()
            assert app.timer_value_label.cget("fg") == app.palette["danger"]
    finally:
        app.close(); root.mainloop()


def test_timer_translations_are_available():
    assert tr("en", "timer.ready") == "READY"
    assert tr("cs", "timer.ready") == "PŘIPRAVEN"
    assert "1–600" in tr("en", "settings.athlete_timer_duration_help")
    assert tr("cs", "settings.athlete_timer_hotkey").startswith("Spustit")
