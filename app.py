from __future__ import annotations

import argparse
from pathlib import Path
import queue
import random
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from src.attempts import AttemptManager
from src.activation import StartupAuthorizationCheck, check_startup_authorization
from src.capture import CaptureEngine
from src.config import load_config
from src.main_window import MainWindow
from src.models import AttemptState
from src.licensing import ensure_license_or_trial
from src.portable_paths import crash_log_path, prepare_config_path, runtime_log_path
from src.ring_buffer import TimeRingBuffer
from src.runtime_diagnostics import configure_runtime_logging, log_event
from src.theme import ThemeManager, show_themed_info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live replay for long-jump take-off decisions")
    parser.add_argument("--config", default=None, help="Path to config.json")
    parser.add_argument("--synthetic", action="store_true", help="Use the built-in synthetic 120 fps camera")
    parser.add_argument("--self-test", action="store_true", help="Run a headless pipeline and attempt-cache test")
    parser.add_argument("--self-test-report", default=None, help="Write self-test output to a text file")
    parser.add_argument("--windowed", action="store_true", help="Ignore fullscreen from config.json")
    parser.add_argument("--splash-preview", action="store_true", help="Show only the startup splash preview")
    parser.add_argument("--startup-camera-index", type=int, default=None, help=argparse.SUPPRESS)
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
        ThemeManager(root).apply("dark")
        show_themed_info(root, "Long Jump Replay", message)
        root.destroy()
    except Exception:
        try:
            if sys.stderr: sys.stderr.write(message + "\n")
        except Exception: pass


def _runtime_asset_path(relative: str) -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return bundle_root / relative


def _animate_splash_window(root: tk.Tk, splash: tk.Toplevel, width: int, height: int, opening: bool, duration_ms: int | None = None) -> None:
    """Keep the compatibility hook, but show and hide the splash instantly."""
    screen_w, screen_h = splash.winfo_screenwidth(), splash.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    try:
        splash.geometry(f"{width}x{height}+{x}+{y}")
        if opening:
            splash.deiconify()
            splash.update_idletasks()
        else:
            splash.withdraw()
    except tk.TclError:
        return


def _startup_splash(root: tk.Tk, language: str = "en") -> tuple[tk.Toplevel, tk.Label, ttk.Progressbar, tk.Label]:
    """Create a cinematic, branded startup screen while workers and the UI load."""
    splash = tk.Toplevel(root)
    splash.withdraw()
    splash.overrideredirect(True)
    splash.configure(bg="#0b111b")
    try:
        splash.attributes("-topmost", True)
    except tk.TclError:
        pass
    width, height = 820, 450
    screen_w, screen_h = splash.winfo_screenwidth(), splash.winfo_screenheight()
    splash.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 2)}")
    canvas = tk.Canvas(splash, width=width, height=height, highlightthickness=0, bg="#0b111b")
    canvas.pack(fill="both", expand=True)
    hero_path = _runtime_asset_path("assets/long_jump_splash.png")
    if hero_path.exists():
        with Image.open(hero_path) as source:
            source = source.convert("RGB")
            scale = max(width / source.width, height / source.height)
            resized = source.resize((round(source.width * scale), round(source.height * scale)), Image.Resampling.LANCZOS)
            left = max(0, (resized.width - width) // 2)
            top = max(0, (resized.height - height) // 2)
            photo = ImageTk.PhotoImage(resized.crop((left, top, left + width, top + height)), master=splash)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        splash._splash_photo = photo  # keep the Tk image alive
    canvas.create_rectangle(0, 0, 430, height, fill="#08111d", outline="")
    canvas.create_rectangle(0, height - 3, width, height, fill="#4f8cff", outline="")
    canvas.create_rectangle(40, 52, 112, 56, fill="#4f8cff", outline="")
    tk.Label(canvas, text="LJR  /  3.2", bg="#08111d", fg="#78a8ff", font=("Consolas", 10, "bold")).place(x=40, y=72)
    canvas.create_text(38, 98, text="LONG JUMP", anchor="nw", fill="#f4f7fb", font=("Segoe UI Semibold", 29))
    canvas.create_text(38, 148, text="REPLAY", anchor="nw", fill="#4f8cff", font=("Segoe UI Semibold", 29))
    subtitle = "STANOVIŠTĚ KONTROLY PŘEŠLAPŮ" if language == "cs" else "FOUL REVIEW STATION"
    preparing = "Připravuji stanoviště rozhodčího…" if language == "cs" else "Preparing judge station…"
    tk.Label(canvas, text=subtitle, bg="#08111d", fg="#8fa6c4", font=("Segoe UI", 10)).place(x=42, y=207)
    tk.Label(canvas, text="PRECISION REVIEW  ·  LIVE CAPTURE  ·  EVIDENCE", bg="#08111d", fg="#607b9f", font=("Consolas", 8)).place(x=42, y=236)
    tk.Label(canvas, text="STARTUP", bg="#162944", fg="#a9c8ff", font=("Consolas", 8, "bold"), padx=8, pady=3).place(x=42, y=282)
    status = tk.Label(canvas, text=preparing, bg="#08111d", fg="#d4e0ef", font=("Segoe UI", 10), anchor="w")
    status.place(x=42, y=328)
    style = ttk.Style(root)
    style.configure("Startup.Horizontal.TProgressbar", troughcolor="#1e2b3d", background="#4f8cff", lightcolor="#78a8ff", darkcolor="#245fc7", borderwidth=0)
    progress = ttk.Progressbar(canvas, mode="determinate", maximum=100, value=0, length=330, style="Startup.Horizontal.TProgressbar")
    progress.place(x=42, y=360)
    action = tk.Label(canvas, text="", bg="#0d1a2b", fg="#8faed1", font=("Consolas", 8), anchor="w", padx=10, pady=5, width=39)
    action.place(x=42, y=394)
    splash.update_idletasks()
    _animate_splash_window(root, splash, width, height, opening=True)
    root.update()
    return splash, status, progress, action


def _check_license_with_splash(
    root: tk.Tk,
    splash: tk.Toplevel,
    status: tk.Label,
    progress: ttk.Progressbar,
    action: tk.Label,
    language: str,
) -> StartupAuthorizationCheck:
    """Run the network check off the Tk thread while keeping startup responsive."""
    results: queue.Queue[StartupAuthorizationCheck] = queue.Queue(maxsize=1)

    def check() -> None:
        try:
            results.put(check_startup_authorization())
        except Exception:  # noqa: BLE001 - an unexpected check failure must fail closed
            results.put(StartupAuthorizationCheck("rejected", "startup_check_failed", None))

    worker = threading.Thread(target=check, name="license-startup-check", daemon=True)
    worker.start()
    started = time.monotonic()
    is_cs = language == "cs"
    status.configure(text="Ověřuji licenci…" if is_cs else "Checking licence…")
    action.configure(text="Kontroluji zařízení a platnost plánu" if is_cs else "Confirming this device and plan status")
    progress.configure(value=6.0)

    while worker.is_alive():
        elapsed = time.monotonic() - started
        progress.configure(value=min(24.0, 6.0 + (elapsed / 15.0) * 18.0))
        splash.update_idletasks()
        root.update()
        time.sleep(0.025)
    worker.join(timeout=0.1)
    result = results.get_nowait()

    if result.state == "verified":
        status.configure(text="Licence ověřena" if is_cs else "Licence verified")
        action.configure(text="Zařízení aktivní  ·  plán platný" if is_cs else "Device active  ·  plan valid")
    elif result.state == "cached":
        status.configure(text="Offline licence přijata" if is_cs else "Offline licence accepted")
        action.configure(text="Server není dostupný  ·  místní autorizace je platná" if is_cs else "Server unavailable  ·  signed authorization is valid")
    else:
        status.configure(text="Je nutná aktivace" if is_cs else "Activation required")
        action.configure(text="Otevřu bezpečnou aktivaci e-mailem" if is_cs else "Opening secure email activation")
    progress.configure(value=28.0)
    splash.update_idletasks()
    return result


def main() -> int:
    args = parse_args()
    config_path = prepare_config_path(args.config)
    logger = configure_runtime_logging(runtime_log_path(config_path))
    log_event(logger, "application_start", synthetic=bool(args.synthetic), self_test=bool(args.self_test))
    previous_thread_hook = threading.excepthook

    def thread_exception(args: threading.ExceptHookArgs) -> None:
        logger.error(
            "worker_thread_failure",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            extra={"event_data": {"event": "worker_thread_failure", "thread_name": args.thread.name if args.thread else "unknown"}},
        )
        previous_thread_hook(args)

    threading.excepthook = thread_exception
    if args.self_test:
        result = run_self_test(config_path, args.self_test_report)
        log_event(logger, "self_test_complete", exit_code=result)
        return result
    try:
        config = load_config(config_path)
        if args.splash_preview:
            root = tk.Tk()
            root.withdraw()
            splash, splash_status, preview_progress, preview_action = _startup_splash(root, config.general.language)
            splash_status.configure(text="Splash preview — press Esc to close")
            preview_progress.configure(value=68)
            preview_action.configure(text="Preview mode  ·  press Esc to close")
            def close_preview(_event=None) -> None:
                _animate_splash_window(root, splash, 820, 450, opening=False)
                root.destroy()
            splash.bind("<Escape>", close_preview)
            root.mainloop()
            return 0
        persistent_camera_source = config.camera.source_type if args.synthetic else None
        if args.synthetic: config.camera.source_type = "synthetic"
        if args.windowed: config.display.fullscreen = False
        root = tk.Tk()
        root.withdraw()
        splash, splash_status, splash_progress, splash_action = _startup_splash(root, config.general.language)
        try:
            is_cs = config.general.language == "cs"
            if getattr(sys, "frozen", False):
                startup_check = _check_license_with_splash(
                    root,
                    splash,
                    splash_status,
                    splash_progress,
                    splash_action,
                    config.general.language,
                )
                if not startup_check.allowed:
                    try:
                        splash.attributes("-topmost", False)
                    except tk.TclError:
                        pass
                    splash.withdraw()
                    if not ensure_license_or_trial(root, config.general.language, startup_check):
                        root.destroy()
                        return 2
                    splash.deiconify()
                    try:
                        splash.attributes("-topmost", True)
                    except tk.TclError:
                        pass
                    splash_status.configure(text="Aktivace dokončena" if is_cs else "Activation complete")
                    splash_action.configure(text="Tento počítač je připraven" if is_cs else "This computer is ready")
                    splash_progress.configure(value=30.0)
                    splash.update_idletasks()

            actions = (
                ("Načítám vizuální systém…", "Loading visual system…"),
                ("Připravuji přehrávání…", "Preparing replay engine…"),
                ("Kontroluji ovládací prvky…", "Checking operator controls…"),
                ("Spouštím kamerové služby…", "Warming up camera services…"),
            )
            preparation_seconds = random.uniform(0.5, 2.0)
            preparation_started = time.perf_counter()
            while True:
                elapsed = time.perf_counter() - preparation_started
                ratio = min(1.0, elapsed / preparation_seconds)
                splash_progress.configure(value=30.0 + ratio * 52.0)
                index = min(len(actions) - 1, int(ratio * len(actions)))
                splash_action.configure(text=actions[index][0 if is_cs else 1])
                splash_status.configure(text="Připravuji stanoviště…" if is_cs else "Preparing judge station…")
                splash.update_idletasks()
                if ratio >= 1.0:
                    break
                time.sleep(0.025)

            splash_progress.configure(value=86.0)
            splash_action.configure(text="Dokončuji spuštění…" if is_cs else "Starting the judge station…")
            splash.update_idletasks()
            MainWindow(
                root,
                config,
                config_path,
                persistent_camera_source_type=persistent_camera_source,
                startup_camera_index=args.startup_camera_index,
            )
            splash_status.configure(text="Připraveno" if is_cs else "Ready")
            splash_action.configure(text="Hotovo  ·  otevírám stanoviště" if is_cs else "Ready  ·  opening judge station")
            splash_progress.configure(value=100.0)
            splash.update_idletasks()
        finally:
            try:
                _animate_splash_window(root, splash, 820, 450, opening=False)
                splash.destroy()
            except tk.TclError:
                pass
        root.deiconify()
        root.mainloop()
        log_event(logger, "application_exit", exit_code=0)
        return 0
    except Exception as exc:
        details = traceback.format_exc()
        log_path = crash_log_path(config_path)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(details, encoding="utf-8")
        except OSError: pass
        _show_fatal(f"Long Jump Replay could not start.\n\n{exc}\n\nCrash details:\n{log_path}")
        logger.exception("application_failure", extra={"event_data": {"event": "application_failure"}})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
