from __future__ import annotations

import tkinter as tk

from src.config import AppConfig, save_config
from src.main_window import MainWindow
from src.models import AttemptDecision


def test_valid_verdict_offers_skippable_measurement_and_persists_it(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .25, .25
    config.competition.auto_save_evidence = False
    config.competition.prompt_distance_after_valid = True
    config.competition.prompt_wind_after_valid = True
    config.display.window_geometry = "1000x650"
    config.shuttle.enabled = False
    path = tmp_path / "config.json"
    save_config(config, path)

    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    def freeze() -> None:
        app.toggle_freeze()

    def decide_and_measure() -> None:
        app.mark_decision(AttemptDecision.VALID)
        result["strip_opened"] = bool(app._measurement_record_id)
        app.measurement_distance_var.set("621")
        app.measurement_wind_var.set("+1,7")
        app._save_measurement()

    def inspect_and_close() -> None:
        attempt = app.attempts.attempts()[0]
        record = app.adjudication.get_for_attempt(attempt)
        result["record"] = record
        result["strip_closed"] = not bool(app._measurement_record_id)
        app.close()

    root.after(650, freeze)
    root.after(850, decide_and_measure)
    root.after(1100, inspect_and_close)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result["strip_opened"] is True
    assert result["strip_closed"] is True
    assert result["record"].verdict == "Valid"
    assert result["record"].distance_cm == 621
    assert result["record"].wind_tenths == 17


def test_skipping_post_verdict_measurement_returns_live_on_next_athlete(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .25, .25
    config.competition.boys_competitors = 2
    config.competition.girls_enabled = False
    config.competition.auto_save_evidence = False
    config.competition.prompt_distance_after_valid = True
    config.competition.auto_advance_after_decision = False
    config.competition.auto_advance_on_attempt_complete = False
    config.competition.auto_return_live = False
    config.display.window_geometry = "1000x650"
    config.shuttle.enabled = False
    path = tmp_path / "config.json"
    save_config(config, path)

    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    root.after(650, app.toggle_freeze)
    root.after(850, lambda: app.mark_decision(AttemptDecision.VALID))
    root.after(950, app._skip_measurement)

    def inspect_and_close() -> None:
        result["athlete"] = app.competition.current_competitor()
        result["mode"] = app.playback.mode.value
        result["strip_closed"] = not bool(app._measurement_record_id)
        app.close()

    root.after(1150, inspect_and_close)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result == {"athlete": 2, "mode": "LIVE", "strip_closed": True}


def test_competition_board_measurement_popup_edits_centimetres_and_wind(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .25, .25
    config.competition.auto_save_evidence = False
    config.display.window_geometry = "1000x650"
    config.shuttle.enabled = False
    path = tmp_path / "config.json"
    save_config(config, path)

    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    root.after(650, app.toggle_freeze)
    root.after(850, lambda: app.mark_decision(AttemptDecision.VALID))

    def open_and_save_popup() -> None:
        attempt = app.attempts.attempts()[0]
        dialog = app._show_measurement_popup(attempt.adjudication_record_id)
        result["popup_opened"] = bool(dialog and dialog.winfo_exists())
        app._measurement_popup_distance_var.set("634")
        app._measurement_popup_wind_var.set("-0.4")
        assert dialog is not None
        assert app._measurement_popup_save_button is not None
        app._measurement_popup_save_button.invoke()

    def inspect_and_close() -> None:
        attempt = app.attempts.attempts()[0]
        result["record"] = app.adjudication.get_for_attempt(attempt)
        result["popup_closed"] = app._measurement_popup is None
        app.close()

    root.after(1000, open_and_save_popup)
    root.after(1250, inspect_and_close)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result["popup_opened"] is True
    assert result["popup_closed"] is True
    assert result["record"].distance_cm == 634
    assert result["record"].wind_tenths == -4
