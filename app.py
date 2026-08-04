from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import time
import traceback
import tkinter as tk
from tkinter import messagebox

from src.attempts import AttemptManager
from src.capture import CaptureEngine
from src.config import load_config
from src.main_window import MainWindow
from src.models import AttemptState
from src.portable_paths import crash_log_path, prepare_config_path
from src.ring_buffer import TimeRingBuffer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live replay for long-jump take-off decisions")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--synthetic", action="store_true", help="Use the built-in synthetic 120 fps camera")
    parser.add_argument("--self-test", action="store_true", help="Run a headless pipeline and attempt-cache test")
    parser.add_argument("--self-test-report", default=None, help="Write self-test output to a text file")
    parser.add_argument("--windowed", action="store_true", help="Ignore fullscreen from config.json")
    return parser.parse_args()


def _write_report(lines: list[str], path: str | Path | None) -> None:
    text = "\n".join(lines) + "\n"
    try:
        if sys.stdout: sys.stdout.write(text); sys.stdout.flush()
    except Exception: pass
    if path:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def run_self_test(config_path: Path, report_path: str | Path | None = None) -> int:
    lines: list[str] = []
    def log(text: str) -> None: lines.append(text)
    try:
        config = load_config(config_path)
        config.camera.source_type = "synthetic"
        config.camera.width, config.camera.height, config.camera.fps = 640, 360, 120.0
        config.buffer.duration_seconds, config.buffer.max_memory_mb = 3.0, 512
        config.attempts.pre_seconds, config.attempts.post_seconds = 1.0, .5
        config.attempts.retention_minutes, config.attempts.max_attempts = 1.0, 3
        with tempfile.TemporaryDirectory(prefix="long-jump-replay-2-") as temp:
            ring = TimeRingBuffer(config.buffer.duration_seconds, config.buffer.max_memory_mb)
            capture = CaptureEngine(config.camera, config.buffer, ring)
            events = __import__("queue").Queue()
            attempts = AttemptManager(ring, config.attempts, config.export, Path(temp) / "cache", events)
            attempts.start(); capture.start()
            log("[1/5] Synthetic 120 fps capture started")
            time.sleep(1.6)
            stats = capture.stats(); buffer_stats = ring.stats()
            log(f"[2/5] capture={stats.capture_fps:.1f} fps, encoded={stats.encode_fps:.1f} fps, buffer={buffer_stats.frame_count} frames, drops={stats.queue_drops}")
            if buffer_stats.frame_count < 60 or stats.last_error:
                raise RuntimeError(stats.last_error or "Too few frames in the live buffer")
            attempt = attempts.create_attempt()
            if attempt is None: raise RuntimeError("Could not create an attempt")
            log(f"[3/5] Attempt #{attempt.attempt_id} pinned at frame {attempt.freeze_frame_index}")
            deadline = time.time() + 15
            ready = None
            while time.time() < deadline:
                ready = attempts.get_attempt(attempt.attempt_id)
                if ready and ready.state in {AttemptState.READY, AttemptState.EXPORTED}: break
                if ready and ready.state is AttemptState.ERROR: raise RuntimeError(ready.error)
                time.sleep(.1)
            if not ready or ready.state is not AttemptState.READY:
                raise RuntimeError("Temporary MP4 attempt was not completed")
            if not ready.temp_video_path or not ready.temp_video_path.exists():
                raise RuntimeError("Temporary attempt video does not exist")
            frame = attempts.get_frame(ready.attempt_id, ready.freeze_frame_index)
            if frame.frame_bgr is None: raise RuntimeError("Could not read the freeze frame from temporary MP4")
            log(f"[4/5] temp MP4={ready.temp_video_path.name}, {ready.frame_count} frames @ {ready.fps:.1f} fps")
            export_dir = Path(temp) / "exports"
            if not attempts.request_export(ready.attempt_id, export_dir): raise RuntimeError("Export request failed")
            deadline = time.time() + 10
            exported = None
            while time.time() < deadline:
                exported = attempts.get_attempt(ready.attempt_id)
                if exported and exported.state is AttemptState.EXPORTED: break
                if exported and exported.state is AttemptState.ERROR: raise RuntimeError(exported.error)
                time.sleep(.1)
            if not exported or not exported.export_path or not exported.export_path.exists():
                raise RuntimeError("Final attempt export was not created")
            alive = attempts.stop(1.0) + capture.stop(2.0)
            log(f"[5/5] export={exported.export_path.name}; remaining workers={alive or 'none'}")
        log("SELF-TEST: OK")
        _write_report(lines, report_path)
        return 0
    except Exception:
        log("SELF-TEST: FAILED")
        log(traceback.format_exc())
        _write_report(lines, report_path)
        return 10


def _show_fatal(message: str) -> None:
    try:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Long Jump Replay", message)
        root.destroy()
    except Exception:
        try:
            if sys.stderr: sys.stderr.write(message + "\n")
        except Exception: pass


def main() -> int:
    args = parse_args()
    config_path = prepare_config_path(args.config)
    if args.self_test:
        return run_self_test(config_path, args.self_test_report)
    try:
        config = load_config(config_path)
        persistent_camera_source = config.camera.source_type if args.synthetic else None
        if args.synthetic: config.camera.source_type = "synthetic"
        if args.windowed: config.display.fullscreen = False
        root = tk.Tk()
        MainWindow(root, config, config_path, persistent_camera_source_type=persistent_camera_source)
        root.mainloop()
        return 0
    except Exception as exc:
        details = traceback.format_exc()
        log_path = crash_log_path(config_path)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(details, encoding="utf-8")
        except OSError: pass
        _show_fatal(f"Long Jump Replay could not start.\n\n{exc}\n\nCrash details:\n{log_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
