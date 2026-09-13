import time
import tkinter as tk
from types import SimpleNamespace
from tkinter import ttk

from src.camera_devices import CameraDevice
from src.config import MIN_TIMELINE_HEIGHT, AppConfig, load_config, save_config
from src.main_window import MainWindow
from src.playback import PlaybackMode


def test_capture_warning_is_compact_for_the_status_row():
    app = object.__new__(MainWindow)
    app.config = SimpleNamespace(camera=SimpleNamespace(fps=120))
    stats = SimpleNamespace(captured_frames=100, capture_fps=80.2, queue_drops=3, last_error="")

    assert app._compact_capture_warning(stats) == "! LOW FPS 80/120 | DROPS 3"


def test_takeoff_failure_notice_is_visible_only_for_the_active_frozen_attempt():
    root = tk.Tk()
    try:
        app = object.__new__(MainWindow)
        app.playback = SimpleNamespace(mode=PlaybackMode.ATTEMPT, attempt_id=7)
        app.assist_warning_var = tk.StringVar(root, value="")
        app.assist_warning_label = ttk.Label(root, textvariable=app.assist_warning_var)

        app._set_assist_warning(7)
        assert app.assist_warning_var.get() == "! Take-off Assist failed"
        assert app.assist_warning_label.winfo_manager() == "pack"

        app._clear_assist_warning()
        assert app.assist_warning_var.get() == ""
        assert not app.assist_warning_label.winfo_manager()
    finally:
        root.destroy()


def test_synthetic_cli_override_does_not_replace_saved_camera_source(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    path = tmp_path / "config.json"
    app = object.__new__(MainWindow)
    app.config = config
    app.config_path = path
    app._persistent_camera_source_type = "camera"

    app._save_config_safely()

    assert app.config.camera.source_type == "synthetic"
    assert load_config(path).camera.source_type == "camera"


def test_main_window_closes_from_live_mode(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .3, .2
    config.display.window_geometry = '1000x650'
    config.display.theme = 'dark'
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    started = time.perf_counter()
    root.after(700, app.close)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert time.perf_counter() - started < 5
    assert not app.capture.is_running


def test_main_window_closes_while_attempt_is_collecting(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .25, 2.0
    config.display.window_geometry = '1000x650'
    config.display.theme = 'light'
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    started = time.perf_counter()
    root.after(500, app.toggle_freeze)
    root.after(750, app.close)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert time.perf_counter() - started < 5
    assert not app.capture.is_running


def test_multiple_attempts_can_be_selected_with_action_queue(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .15, .10
    config.display.window_geometry = '1000x650'
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    selected = []
    selection_deadline = time.perf_counter() + 5.0

    def first_freeze():
        app.toggle_freeze()

    def return_and_second_freeze():
        app.return_live()
        app.toggle_freeze()

    def select_previous():
        app.action_queue.put(('select_attempt', -1))

    def inspect_and_close():
        if app.playback.attempt_id != 1 and time.perf_counter() < selection_deadline:
            root.after(50, inspect_and_close)
            return
        selected.append(app.playback.attempt_id)
        app.close()

    root.after(450, first_freeze)
    root.after(900, return_and_second_freeze)
    root.after(1400, select_previous)
    root.after(1700, inspect_and_close)
    root.after(6000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert len(app.attempts.attempts()) >= 2
    assert selected == [1]


def test_gui_attempt_marker_export_and_clean_shutdown(tmp_path):
    from src.models import AttemptState

    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 120
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.attempts.pre_seconds, config.attempts.post_seconds = .20, .10
    config.attempts.cache_directory = 'cache'
    config.export.directory = 'exports'
    config.display.window_geometry = '1000x650'
    config.display.theme = 'dark'
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    def freeze_first():
        app.toggle_freeze()

    def mark_and_export():
        app.add_marker()
        app.export_current_attempt()

    def second_attempt():
        app.return_live()
        app.toggle_freeze()

    def previous_attempt():
        app.action_queue.put(('select_attempt', -1))

    def inspect():
        attempts = app.attempts.attempts()
        result['count'] = len(attempts)
        result['selected'] = app.playback.attempt_id
        result['first'] = attempts[0] if attempts else None
        app.close()

    root.after(500, freeze_first)
    root.after(1300, mark_and_export)
    root.after(1900, second_attempt)
    root.after(2500, previous_attempt)
    root.after(3300, inspect)
    root.after(7500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert result['count'] >= 2
    assert result['selected'] == 1
    first = result['first']
    assert first.markers
    assert first.state in {AttemptState.EXPORTED, AttemptState.READY}
    if first.state is AttemptState.EXPORTED:
        assert first.export_path and first.export_path.exists()
    assert not app.capture.is_running


def test_resizable_panes_start_with_visible_video_and_timeline(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.display.window_geometry = '1100x700'
    config.display.timeline_height = 150
    config.display.show_attempts_panel = False
    config.display.show_timeline = False
    config.display.show_status_bar = False
    config.display.show_live_preview = False
    config.competition.show_competition_board = False
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    sizes = {}

    def inspect():
        sizes['video'] = app.video_host.winfo_height()
        sizes['timeline'] = app.timeline_wrap.winfo_height()
        sizes['timeline_hint'] = app.timeline_hint_label.winfo_height()
        sizes['status'] = app.status_bar.winfo_height()
        sizes['replay_width'] = app.replay_canvas.winfo_width()
        sizes['view_flags'] = (
            app.var_show_attempts.get(), app.var_show_board.get(), app.var_show_timeline.get(),
            app.var_show_live.get(), app.var_show_status.get(),
        )
        app.close()

    root.after(700, inspect)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert sizes['video'] > 250
    assert 140 <= sizes['timeline'] <= 190
    assert sizes['timeline_hint'] <= 2
    assert sizes['status'] >= 20
    assert sizes['replay_width'] > 400
    assert sizes['view_flags'] == (True, True, True, True, True)


def test_withdrawn_startup_waits_for_real_geometry_before_positioning_timeline(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.display.window_geometry = '1100x700'
    config.display.timeline_height = 220
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk(); root.withdraw()
    app = MainWindow(root, config, path)
    sizes = {}

    def inspect():
        sizes['video'] = app.video_host.winfo_height()
        sizes['timeline'] = app.timeline_wrap.winfo_height()
        app.close()

    root.deiconify()
    root.after(700, inspect)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert sizes['video'] > 250
    assert 140 <= sizes['timeline'] <= 190


def test_applying_unchanged_settings_preserves_timeline_size(monkeypatch, tmp_path):
    config = AppConfig()
    config.camera.source_type = 'file'
    config.camera.file_path = str(tmp_path / 'missing-test-video.mp4')
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.display.window_geometry = '1100x700'
    config.general.onboarding_completed = True
    config.shuttle.enabled = False
    monkeypatch.setattr(
        'src.settings_dialog.enumerate_camera_devices',
        lambda current: [CameraDevice(current, 'Current camera')],
    )
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    sizes = {}

    def apply_without_changes():
        root.update_idletasks()
        sizes['before'] = app.timeline_wrap.winfo_height()
        sizes['sash_before'] = app.media_pane.sashpos(0)
        dialog = app.open_settings()
        dialog.update_idletasks()
        dialog._apply(True)
        root.after(350, inspect)

    def inspect():
        root.update_idletasks()
        sizes['after'] = app.timeline_wrap.winfo_height()
        sizes['sash_after'] = app.media_pane.sashpos(0)
        app.close()

    root.after(700, apply_without_changes)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert (sizes['after'], sizes['sash_after']) == (sizes['before'], sizes['sash_before'])


def test_exit_survives_an_out_of_range_timeline_sash(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.display.window_geometry = '1100x700'
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)

    def break_sash_then_close():
        app.media_pane.sashpos(0, 0)
        app.close()

    root.after(500, break_sash_then_close)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert not app.capture.is_running


def test_showing_timeline_restores_a_usable_height(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.display.window_geometry = '1100x700'
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    result = {}

    def hide_then_show():
        app.var_show_timeline.set(False); app.toggle_timeline()
        app.config.display.timeline_height = 100
        app.var_show_timeline.set(True); app.toggle_timeline()

    def inspect():
        result['height'] = app.timeline_wrap.winfo_height()
        result['saved_height'] = app.config.display.timeline_height
        app.close()

    root.after(500, hide_then_show)
    root.after(950, inspect)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
    assert result['height'] >= 140
    assert result['saved_height'] >= MIN_TIMELINE_HEIGHT


def test_window_interaction_suspends_expensive_redraws(tmp_path):
    config = AppConfig()
    config.camera.source_type = 'synthetic'
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.display.window_geometry = '1000x650'
    config.shuttle.enabled = False
    path = tmp_path / 'config.json'
    save_config(config, path)
    root = tk.Tk()
    app = MainWindow(root, config, path)
    state = {}

    def inspect_suspended():
        app._begin_window_interaction()
        state['during'] = (
            app._window_interacting,
            app.replay_canvas._render_suspended,
            app.live_canvas._render_suspended,
            app.timeline._render_suspended,
        )
        app._end_window_interaction()
        state['after'] = (
            app._window_interacting,
            app.replay_canvas._render_suspended,
            app.live_canvas._render_suspended,
            app.timeline._render_suspended,
        )
        app.close()

    root.after(450, inspect_suspended)
    root.after(5500, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()

    assert state['during'] == (True, True, True, True)
    assert state['after'] == (False, False, False, False)
