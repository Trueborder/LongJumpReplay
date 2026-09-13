from __future__ import annotations

import argparse
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk

ACTIVATION_STARTUP_MINIMUM_SECONDS = 2.0


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
    from src.attempts import AttemptManager
    from src.capture import CaptureEngine
    from src.config import load_config
    from src.models import AttemptState
    from src.ring_buffer import TimeRingBuffer
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
    from src.theme import ThemeManager, show_themed_info
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


def _rounded_rectangle(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: float, **kwargs) -> int:
    radius = max(0.0, min(float(radius), (x2 - x1) / 2, (y2 - y1) / 2))
    points = (
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    )
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class RoundedProgressBar(tk.Canvas):
    """Compact dark determinate bar with a real numeric Tk-compatible value."""

    def __init__(self, master: tk.Misc, *, length: int = 336, height: int = 12, maximum: float = 100.0) -> None:
        super().__init__(
            master, width=length, height=height, background="#0d1928",
            highlightthickness=0, borderwidth=0, takefocus=False,
        )
        self._value = 0.0
        self._maximum = max(1.0, float(maximum))
        self._length = length
        self._height = height
        self.bind("<Configure>", lambda _event: self._draw(), add="+")
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(2, self.winfo_width() if self.winfo_width() > 1 else self._length)
        height = max(4, self.winfo_height() if self.winfo_height() > 1 else self._height)
        radius = height / 2
        _rounded_rectangle(self, 0, 0, width, height, radius, fill="#263a55", outline="")
        _rounded_rectangle(self, 1, 1, width - 1, height - 1, radius - 1, fill="#111f31", outline="")
        fraction = min(1.0, max(0.0, self._value / self._maximum))
        if fraction <= 0:
            return
        fill_width = max(height - 2, (width - 2) * fraction)
        _rounded_rectangle(self, 1, 1, min(width - 1, fill_width), height - 1, radius - 1, fill="#4f8cff", outline="")

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        if "value" in kwargs:
            self._value = min(self._maximum, max(0.0, float(kwargs.pop("value"))))
        if "maximum" in kwargs:
            self._maximum = max(1.0, float(kwargs.pop("maximum")))
        result = super().configure(**kwargs) if kwargs else None
        self._draw()
        return result

    config = configure

    def cget(self, key: str):  # type: ignore[override]
        if key == "value":
            return self._value
        if key == "maximum":
            return self._maximum
        return super().cget(key)

    def stop(self) -> None:
        return


class RoundedActionButton(tk.Canvas):
    """Keyboard-accessible compact action used by the unthemed startup window."""

    def __init__(self, master: tk.Misc, text: str, command, *, width: int = 96, height: int = 32) -> None:
        super().__init__(
            master, width=width, height=height, background="#0d1928", cursor="hand2",
            highlightthickness=0, borderwidth=0, takefocus=True,
        )
        self._text = text
        self._command = command
        self._hovered = False
        self._pressed = False
        self._disabled = False
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda _event: self._draw())
        self.bind("<FocusOut>", lambda _event: self._draw())
        self.bind("<Return>", self._keyboard_invoke)
        self.bind("<space>", self._keyboard_invoke)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(2, self.winfo_width() if self.winfo_width() > 1 else int(self["width"]))
        height = max(2, self.winfo_height() if self.winfo_height() > 1 else int(self["height"]))
        fill = "#111a28" if self._disabled else "#142238" if self._pressed else "#1c3150" if self._hovered else "#17263b"
        border = "#273448" if self._disabled else "#4f8cff" if self.focus_get() is self else "#58789f" if self._hovered else "#354b68"
        text = "#66758a" if self._disabled else "#f4f7fb"
        _rounded_rectangle(self, 1, 1, width - 1, height - 1, 8, fill=fill, outline=border, width=1)
        self.create_text(width / 2, height / 2, text=self._text, fill=text, font=("Segoe UI Semibold", 9))

    def _enter(self, _event=None) -> None:
        if not self._disabled:
            self._hovered = True
            self._draw()

    def _leave(self, _event=None) -> None:
        self._hovered = self._pressed = False
        self._draw()

    def _press(self, _event=None) -> None:
        if not self._disabled:
            self.focus_set()
            self._pressed = True
            self._draw()

    def _release(self, event=None) -> None:
        was_pressed = self._pressed
        self._pressed = False
        inside = event is None or (0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height())
        self._draw()
        if was_pressed and inside:
            self.invoke()

    def _keyboard_invoke(self, _event=None) -> str:
        self.invoke()
        return "break"

    def invoke(self):
        if not self._disabled and self._command:
            return self._command()
        return None

    def configure(self, cnf=None, **kwargs):  # type: ignore[override]
        if cnf:
            kwargs.update(cnf)
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._disabled = str(kwargs.pop("state")) == "disabled"
        result = super().configure(**kwargs) if kwargs else None
        self._draw()
        return result

    config = configure


def _windows_client_animations_enabled() -> bool:
    """Honor Windows' client-area animation accessibility preference."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        enabled = ctypes.c_int()
        # SPI_GETCLIENTAREAANIMATION
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)
    except (AttributeError, OSError):
        pass
    return True


def _strong_ease_out(progress: float) -> float:
    """Evaluate cubic-bezier(0.23, 1, 0.32, 1) at a time fraction."""
    target = min(1.0, max(0.0, float(progress)))

    def component(value: float, first: float, second: float) -> float:
        inverse = 1.0 - value
        return 3.0 * inverse * inverse * value * first + 3.0 * inverse * value * value * second + value ** 3

    low, high = 0.0, 1.0
    for _ in range(12):
        parameter = (low + high) / 2.0
        if component(parameter, 0.23, 0.32) < target:
            low = parameter
        else:
            high = parameter
    return component((low + high) / 2.0, 1.0, 1.0)


def _animate_splash_window(root: tk.Tk, splash: tk.Toplevel, width: int, height: int, opening: bool, duration_ms: int | None = None) -> None:
    """Fade in the occasional startup surface without animating its geometry."""
    screen_w, screen_h = splash.winfo_screenwidth(), splash.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    try:
        splash.geometry(f"{width}x{height}+{x}+{y}")
        if opening:
            animate = _windows_client_animations_enabled()
            if animate:
                splash.attributes("-alpha", 0.0)
            splash.deiconify()
            splash.update_idletasks()
            if animate:
                duration = 200 if duration_ms is None else max(0, int(duration_ms))
                if duration > 0:
                    started = time.perf_counter()
                    while True:
                        elapsed = (time.perf_counter() - started) * 1000.0
                        fraction = min(1.0, elapsed / duration)
                        splash.attributes("-alpha", _strong_ease_out(fraction))
                        splash.update()
                        if fraction >= 1.0:
                            break
                        time.sleep(0.012)
                splash.attributes("-alpha", 1.0)
        else:
            splash.withdraw()
    except tk.TclError:
        try:
            splash.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        return


class StartupWindow:
    PHASE_RANGES = {
        "settings": (0.0, 10.0),
        "components": (10.0, 30.0),
        "licence_update": (30.0, 50.0),
        "interface": (50.0, 90.0),
        "services": (90.0, 100.0),
    }

    def __init__(self, root: tk.Tk, language: str = "en", details_expanded: bool = False) -> None:
        from src.progress import ProgressController

        self.root = root
        self.language = language
        self.is_cs = language == "cs"
        self.overall = ProgressController()
        self.task = ProgressController()
        self._phase_id = ""
        self._history: list[str] = []
        self._details_expanded = details_expanded
        self._preference_callback = None
        splash = self.window = tk.Toplevel(root)
        splash.withdraw()
        splash.overrideredirect(True)
        splash.configure(bg="#07111e")
        try: splash.attributes("-topmost", True)
        except tk.TclError: pass
        self.width, self.closed_height, self.expanded_height = 840, 460, 600
        self._center(self.closed_height)
        canvas = self.canvas = tk.Canvas(splash, width=self.width, height=self.closed_height, highlightthickness=0, bg="#07111e")
        canvas.pack(fill="x")
        hero_path = _runtime_asset_path("assets/long_jump_splash.png")
        if hero_path.exists():
            try:
                from PIL import Image, ImageDraw, ImageEnhance, ImageOps, ImageTk

                with Image.open(hero_path) as source:
                    hero = ImageOps.fit(source.convert("RGB"), (self.width, self.closed_height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.52))
                hero = ImageEnhance.Brightness(hero).enhance(0.72).convert("RGBA")
                shade = Image.new("RGBA", hero.size, (0, 0, 0, 0))
                shade_draw = ImageDraw.Draw(shade)
                for x in range(420, 506):
                    shade_draw.line((x, 0, x, self.closed_height), fill=(7, 17, 30, int(185 * (1 - (x - 420) / 86) ** 2)))
                shade_draw.rectangle((420, self.closed_height - 105, self.width, self.closed_height), fill=(4, 11, 20, 44))
                hero = Image.alpha_composite(hero, shade)
                photo = ImageTk.PhotoImage(hero, master=splash)
                canvas.create_image(0, 0, image=photo, anchor="nw")
                splash._splash_photo = photo
            except (OSError, tk.TclError):
                pass
        canvas.create_rectangle(0, 0, 420, self.closed_height, fill="#07111e", outline="")
        canvas.create_rectangle(0, self.closed_height - 3, self.width, self.closed_height, fill="#4f8cff", outline="")
        canvas.create_rectangle(40, 38, 104, 42, fill="#4f8cff", outline="")
        tk.Label(canvas, text="LJR / STARTUP", bg="#07111e", fg="#78a8ff", font=("Consolas", 9, "bold")).place(x=40, y=54)
        canvas.create_text(38, 86, text="LONG JUMP", anchor="nw", fill="#f4f7fb", font=("Segoe UI Semibold", 25))
        canvas.create_text(38, 126, text="REPLAY", anchor="nw", fill="#4f8cff", font=("Segoe UI Semibold", 25))
        subtitle = "STANOVIŠTĚ KONTROLY PŘEŠLAPŮ" if self.is_cs else "FOUL REVIEW STATION"
        tk.Label(canvas, text=subtitle, bg="#07111e", fg="#9eb1ca", font=("Segoe UI", 9)).place(x=41, y=174)
        tk.Label(canvas, text="REVIEW  ·  BUFFER  ·  DECIDE", bg="#07111e", fg="#6685ad", font=("Consolas", 8)).place(x=41, y=199)
        _rounded_rectangle(canvas, 32, 231, 388, 414, 16, fill="#0d1928", outline="#22344d", width=1)
        tk.Label(canvas, text=self._txt("STARTING LONGJUMPREPLAY", "SPOUŠTÍM LONGJUMPREPLAY"), bg="#0d1928", fg="#78a8ff", font=("Consolas", 8, "bold")).place(x=48, y=244)
        self.overall_label = tk.Label(canvas, text=self._txt("Overall startup progress", "Celkový průběh spuštění"), bg="#0d1928", fg="#dce6f3", font=("Segoe UI", 9), anchor="w")
        self.overall_label.place(x=48, y=270)
        self.overall_bar = RoundedProgressBar(canvas, length=324)
        self.overall_bar.place(x=48, y=293)
        self.task_label = tk.Label(canvas, text=self._txt("Preparing settings…", "Připravuji nastavení…"), bg="#0d1928", fg="#dce6f3", font=("Segoe UI", 9), anchor="w")
        self.task_label.place(x=48, y=319)
        self.task_bar = RoundedProgressBar(canvas, length=324)
        self.task_bar.place(x=48, y=342)
        self.detail_label = tk.Label(canvas, text="", bg="#0d1928", fg="#8faed1", font=("Segoe UI", 8), anchor="w", width=48)
        self.detail_label.place(x=48, y=365)
        self.details_button = RoundedActionButton(canvas, "", self._toggle_details, width=96, height=30)
        self.details_button.place(x=40, y=420)
        self.details_frame = tk.Frame(splash, bg="#091522", padx=38, pady=12)
        self.history = tk.Text(
            self.details_frame, height=6, wrap="word", state="disabled", takefocus=False,
            bg="#0d1928", fg="#aebed2", insertbackground="#f4f7fb", relief="flat",
            borderwidth=0, padx=12, pady=10, font=("Segoe UI", 9),
        )
        self.history.pack(fill="both", expand=True)
        self._sync_details()
        splash.update_idletasks()
        _animate_splash_window(
            root, splash, self.width,
            self.expanded_height if self._details_expanded else self.closed_height,
            opening=True,
        )
        root.update()
        self._painted_at = time.monotonic()

    def _txt(self, english: str, czech: str) -> str:
        return czech if self.is_cs else english

    def _center(self, height: int) -> None:
        screen_w, screen_h = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        self.window.geometry(f"{self.width}x{height}+{max(0, (screen_w-self.width)//2)}+{max(0, (screen_h-height)//2)}")

    def set_preference_callback(self, callback) -> None:
        self._preference_callback = callback

    def _toggle_details(self) -> None:
        self._details_expanded = not self._details_expanded
        self._sync_details()
        if self._preference_callback: self._preference_callback(self._details_expanded)

    def _sync_details(self) -> None:
        self.details_button.configure(text=self._txt("Hide details", "Skrýt podrobnosti") if self._details_expanded else self._txt("Details", "Podrobnosti"))
        if self._details_expanded:
            self.details_frame.pack(fill="both", expand=True)
            self._center(self.expanded_height)
        else:
            self.details_frame.pack_forget()
            self._center(self.closed_height)

    def emit(self, event) -> None:
        from src.progress import ProgressState

        phase_start, phase_end = self.PHASE_RANGES[event.phase_id]
        fraction = min(1.0, max(0.0, event.completed_units / max(1, event.total_units)))
        overall_value = phase_start + (phase_end - phase_start) * fraction
        if event.state is not ProgressState.COMPLETED:
            overall_value = min(overall_value, 99.0)
        self.overall_bar.configure(value=max(float(self.overall_bar.cget("value")), overall_value))
        if event.phase_id != self._phase_id:
            self._phase_id = event.phase_id
            self.task_bar.configure(value=0)
        self.task_bar.configure(value=max(float(self.task_bar.cget("value")), fraction * 100.0))
        self.task_label.configure(text=event.operation_label)
        self.detail_label.configure(text=event.detail)
        history_line = event.detail or event.operation_label
        if history_line and (not self._history or self._history[-1] != history_line):
            self._history.append(history_line)
            self.history.configure(state="normal")
            self.history.insert("end", history_line.rstrip("…") + "\n")
            self.history.see("end")
            self.history.configure(state="disabled")
        # Redraw idle work without entering a nested event loop. Once camera
        # polling starts, root.update() can keep consuming recurring callbacks
        # forever and prevent the splash from reaching destroy().
        self.window.update_idletasks()

    def show_failure(self, log_path: Path) -> None:
        self.task_bar.stop()
        self.task_label.configure(text=self._txt("LongJumpReplay could not start", "LongJumpReplay se nepodařilo spustit"), fg="#ff9b9b")
        self.detail_label.configure(text=self._txt("Open the log for details, then exit and try again.", "Otevřete protokol s podrobnostmi, ukončete aplikaci a zkuste to znovu."))
        self.details_button.place_forget()
        RoundedActionButton(self.canvas, self._txt("Open log", "Otevřít protokol"), command=lambda: os.startfile(log_path), width=110).place(x=40, y=420)
        RoundedActionButton(self.canvas, self._txt("Exit", "Ukončit"), command=self.root.destroy, width=86).place(x=158, y=420)
        self.window.update_idletasks()

    def destroy(self) -> None:
        try:
            self.window.attributes("-topmost", False)
            self.window.withdraw()
            self.window.destroy()
        except tk.TclError: pass

    def update_idletasks(self) -> None:
        self.window.update_idletasks()

    def wait_until_visible_for(self, minimum_seconds: float) -> None:
        """Keep the painted startup window responsive for a minimum duration."""
        remaining = self._painted_at + max(0.0, minimum_seconds) - time.monotonic()
        if remaining <= 0:
            return
        elapsed = tk.BooleanVar(master=self.root, value=False)
        self.root.after(int(remaining * 1000) + 1, elapsed.set, True)
        self.root.wait_variable(elapsed)


def _startup_splash(root: tk.Tk, language: str = "en", details_expanded: bool = False) -> StartupWindow:
    """Create the detailed modal startup window."""
    return StartupWindow(root, language, details_expanded)


def _close_boot_splash() -> None:
    try:
        import pyi_splash
        if pyi_splash.is_alive(): pyi_splash.close()
    except (ImportError, RuntimeError):
        pass


def _check_license_with_splash(
    root: tk.Tk,
    splash: StartupWindow,
    language: str,
) -> object:
    """Run the network check off the Tk thread while keeping startup responsive."""
    from src.activation import StartupAuthorizationCheck, check_startup_authorization
    status, progress, action = splash.task_label, splash.task_bar, splash.detail_label
    results: queue.Queue[StartupAuthorizationCheck] = queue.Queue(maxsize=1)

    def check() -> None:
        try:
            results.put(check_startup_authorization())
        except Exception:  # noqa: BLE001 - an unexpected check failure must fail closed
            results.put(StartupAuthorizationCheck("rejected", "startup_check_failed", None))

    worker = threading.Thread(target=check, name="license-startup-check", daemon=True)
    worker.start()
    is_cs = language == "cs"
    status.configure(text="Ověřuji licenci…" if is_cs else "Checking licence…")
    action.configure(text="Kontroluji zařízení a platnost plánu" if is_cs else "Confirming this device and plan status")
    progress.configure(value=25.0)

    while worker.is_alive():
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
    progress.configure(value=75.0)
    splash.update_idletasks()
    return result


def main() -> int:
    """Start with real milestones and keep the boot splash until Tk has painted."""
    from src.config import load_config, save_config
    from src.portable_paths import crash_log_path, prepare_config_path, runtime_log_path
    from src.progress import ProgressState, StartupProgressEvent
    from src.runtime_diagnostics import configure_runtime_logging, log_event

    args = parse_args()
    config_path = prepare_config_path(args.config)
    logger = configure_runtime_logging(runtime_log_path(config_path))
    log_event(logger, "application_start", synthetic=bool(args.synthetic), self_test=bool(args.self_test))
    previous_thread_hook = threading.excepthook

    def thread_exception(hook_args: threading.ExceptHookArgs) -> None:
        logger.error(
            "worker_thread_failure",
            exc_info=(hook_args.exc_type, hook_args.exc_value, hook_args.exc_traceback),
            extra={"event_data": {"event": "worker_thread_failure", "thread_name": hook_args.thread.name if hook_args.thread else "unknown"}},
        )
        previous_thread_hook(hook_args)

    threading.excepthook = thread_exception
    if args.self_test:
        _close_boot_splash()
        result = run_self_test(config_path, args.self_test_report)
        log_event(logger, "self_test_complete", exit_code=result)
        return result

    root: tk.Tk | None = None
    startup: StartupWindow | None = None
    try:
        config = load_config(config_path)
        root = tk.Tk(); root.withdraw()
        startup = _startup_splash(root, config.general.language, config.general.progress_details_expanded)
        _close_boot_splash()
        is_cs = config.general.language == "cs"

        def remember_details(expanded: bool) -> None:
            config.general.progress_details_expanded = expanded
            save_config(config, config_path)

        startup.set_preference_callback(remember_details)
        startup.emit(StartupProgressEvent("settings", "Nastavuji protokolování a předvolby…" if is_cs else "Loading settings and logging…", 1, 1, .1, "Nastavení a protokolování připraveno" if is_cs else "Settings and logging ready"))
        if args.splash_preview:
            startup.emit(StartupProgressEvent("interface", "Náhled úvodního okna" if is_cs else "Startup window preview", 5, 8, .4, "Stisknutím Esc zavřete" if is_cs else "Press Esc to close"))
            startup.window.bind("<Escape>", lambda _event: root.destroy())
            root.mainloop(); return 0

        startup.emit(StartupProgressEvent("components", "Načítám součásti aplikace…" if is_cs else "Loading application components…", 0, 1, .2))
        # OpenCV, application controllers and the full UI are intentionally
        # imported only after the detailed Tk startup window is visible.
        from src.licensing import ensure_license_or_trial
        from src.main_window import MainWindow
        from src.updater import start_update_check
        startup.emit(StartupProgressEvent("components", "Součásti aplikace načteny" if is_cs else "Application components loaded", 1, 1, .2, "Replay and interface modules ready" if not is_cs else "Moduly replaye a rozhraní jsou připraveny"))

        persistent_camera_source = config.camera.source_type if args.synthetic else None
        if args.synthetic: config.camera.source_type = "synthetic"
        if args.windowed: config.display.fullscreen = False
        update_task = None
        if getattr(sys, "frozen", False):
            update_task = start_update_check()
            startup_check = _check_license_with_splash(root, startup, config.general.language)
            if not startup_check.allowed:
                startup.wait_until_visible_for(ACTIVATION_STARTUP_MINIMUM_SECONDS)
                try: startup.window.attributes("-topmost", False)
                except tk.TclError: pass
                startup.window.withdraw()
                if not ensure_license_or_trial(root, config.general.language, startup_check):
                    root.destroy(); return 2
                startup.window.deiconify()
                try: startup.window.attributes("-topmost", True)
                except tk.TclError: pass
            result = update_task.result()
            detail = (f"Aktualizace {result.release.version} je připravena" if is_cs else f"Update {result.release.version} is ready") if result and result.status == "available" and result.release else ("Kontrola aktualizací pokračuje na pozadí" if is_cs else "Update check continuing in background")
            startup.emit(StartupProgressEvent("licence_update", "Kontrola licence a aktualizací dokončena" if is_cs else "Licence and update checks complete", 4, 4, .2, detail))
        else:
            startup.emit(StartupProgressEvent("licence_update", "Kontroly při spuštění dokončeny" if is_cs else "Startup checks complete", 4, 4, .2, "Zdrojové spuštění" if is_cs else "Source launch"))

        MainWindow(
            root, config, config_path,
            persistent_camera_source_type=persistent_camera_source,
            startup_camera_index=args.startup_camera_index,
            startup_update_task=update_task,
            startup_progress=startup.emit,
        )
        startup.emit(StartupProgressEvent("services", "Připraveno" if is_cs else "Ready", 4, 4, .1, "Stanoviště rozhodčího je připraveno" if is_cs else "Judge station is ready", ProgressState.COMPLETED))
        root.deiconify()
        root.update_idletasks()
        startup.destroy()
        startup = None
        try:
            root.lift()
            root.focus_force()
        except tk.TclError:
            pass
        root.mainloop()
        log_event(logger, "application_exit", exit_code=0)
        return 0
    except Exception:
        details = traceback.format_exc()
        log_path = crash_log_path(config_path)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(details, encoding="utf-8")
        except OSError:
            pass
        logger.exception("application_failure", extra={"event_data": {"event": "application_failure"}})
        _close_boot_splash()
        if startup is not None and root is not None:
            startup.show_failure(log_path)
            try: root.mainloop()
            except tk.TclError: pass
        else:
            _show_fatal(f"Long Jump Replay could not start.\n\nOpen the crash log for details:\n{log_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
