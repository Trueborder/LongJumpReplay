import tkinter as tk

from src.config import AppConfig, save_config
from src.main_window import MainWindow


def test_camera_uses_only_modeless_indeterminate_overlay_and_timeout_actions(tmp_path):
    config = AppConfig()
    config.camera.source_type = "synthetic"
    config.camera.width, config.camera.height, config.camera.fps = 320, 180, 60
    config.buffer.duration_seconds, config.buffer.max_memory_mb = 2, 256
    config.display.window_geometry = "1000x650"
    config.shuttle.enabled = False
    path = tmp_path / "config.json"; save_config(config, path)
    root = tk.Tk(); app = MainWindow(root, config, path)
    root.update_idletasks()
    assert str(app.camera_waiting_progress.cget("mode")) == "indeterminate"
    assert not app.status_progress.winfo_ismapped()
    app._camera_starting = False
    app._camera_input_timed_out = True
    app._displayed_bgr = None
    app._update_camera_input_overlay(True)
    root.update_idletasks()
    assert not app.camera_waiting_frame.winfo_manager()
    assert app.camera_action_frame.winfo_manager() == "place"
    app.close()
    root.after(5000, lambda: root.destroy() if root.winfo_exists() else None)
    root.mainloop()
