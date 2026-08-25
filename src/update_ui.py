"""Non-blocking themed Tk interface for application updates."""

from __future__ import annotations

from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable
from urllib.parse import urlparse

from .theme import configure_popup
from .updater import ReleaseInfo, UpdateCancelled, UpdateError, download_update, skip_version


class UpdateDialog:
    def __init__(self, parent: tk.Misc, release: ReleaseInfo, language: str, on_install_ready: Callable[[Path], None]) -> None:
        self.parent, self.release, self.language = parent, release, language
        self.on_install_ready = on_install_ready
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancel_event = threading.Event()
        self._download_started = 0.0
        self._last_sample: tuple[float, int] | None = None
        self._rate_bytes_per_second: float | None = None
        try:
            self._previous_grab = parent.grab_current()
        except tk.TclError:
            self._previous_grab = None
        self.window = tk.Toplevel(parent)
        self.palette = configure_popup(self.window, parent)
        self.window.title(self._txt("LongJumpReplay update", "Aktualizace LongJumpReplay"))
        self.window.geometry("590x450")
        self.window.minsize(540, 410)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.ask_later)
        body = ttk.Frame(self.window, style="Dialog.TFrame", padding=(24, 22))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=self._txt("UPDATE AVAILABLE", "DOSTUPNÁ AKTUALIZACE"), style="ContextTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text=self._txt(f"LongJumpReplay {release.version} is ready", f"LongJumpReplay {release.version} je připraven"), style="DialogTitle.TLabel").pack(anchor="w", pady=(5, 8))
        size_mb = release.size / (1024 * 1024)
        ttk.Label(body, text=self._txt(f"Installed version can be updated in one step · {size_mb:.1f} MB", f"Nainstalovanou verzi lze aktualizovat v jednom kroku · {size_mb:.1f} MB"), style="DialogBody.TLabel").pack(anchor="w")
        notes_frame = ttk.Frame(body, style="Panel.TFrame", padding=(14, 12))
        notes_frame.pack(fill="both", expand=True, pady=(16, 14))
        ttk.Label(notes_frame, text=self._txt("WHAT'S NEW", "CO JE NOVÉHO"), style="ContextTitle.TLabel").pack(anchor="w")
        notes = release.notes or (self._txt("Reliability and application improvements.", "Vylepšení spolehlivosti a aplikace."),)
        ttk.Label(notes_frame, text="\n".join(f"• {item}" for item in notes), style="Text.TLabel", wraplength=500, justify="left").pack(anchor="w", pady=(8, 0))
        self.status = ttk.Label(body, text="", style="Muted.TLabel")
        self.status.pack(anchor="w")
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress_detail = ttk.Label(body, text="", style="Muted.TLabel")
        self.footer = ttk.Frame(body, style="Dialog.TFrame")
        self.footer.pack(fill="x", pady=(14, 0))
        self.ask_button = ttk.Button(self.footer, text=self._txt("Ask later", "Připomenout příště"), style="Control.TButton", command=self.ask_later)
        self.ask_button.pack(side="left")
        self.skip_button = ttk.Button(self.footer, text=self._txt("Skip this version", "Přeskočit tuto verzi"), style="Control.TButton", command=self.skip)
        self.skip_button.pack(side="right", padx=(8, 0))
        self.install_button = ttk.Button(self.footer, text=self._txt("Install", "Nainstalovat"), style="Accent.TButton", command=self.install)
        self.install_button.pack(side="right", padx=(8, 0))
        self.cancel_button = ttk.Button(self.footer, text=self._txt("Cancel", "Zrušit"), style="Control.TButton", command=self.cancel_download)
        self.window.grab_set()

    def _txt(self, english: str, czech: str) -> str:
        return czech if self.language == "cs" else english

    def ask_later(self) -> None:
        if self.cancel_button.winfo_manager():
            self.cancel_download()
            return
        try:
            self.window.grab_release(); self.window.destroy()
        except tk.TclError:
            pass
        if self._previous_grab is not None:
            try:
                if self._previous_grab.winfo_exists():
                    self._previous_grab.grab_set()
                    self._previous_grab.lift()
            except tk.TclError:
                pass

    def skip(self) -> None:
        skip_version(self.release.version); self.ask_later()

    def install(self) -> None:
        self.cancel_event.clear()
        self._download_started = time.monotonic()
        self._last_sample = None
        self._rate_bytes_per_second = None
        for button in (self.install_button, self.skip_button, self.ask_button): button.configure(state="disabled")
        self.status.configure(text=self._txt("Downloading verified update…", "Stahuji ověřenou aktualizaci…"), style="Muted.TLabel")
        self.progress.configure(value=0)
        self.progress.pack(fill="x", before=self.footer, pady=(12, 0))
        self.progress_detail.pack(anchor="w", before=self.footer, pady=(5, 0))
        self.cancel_button.pack(side="right", padx=(8, 0), before=self.install_button)

        def progress(received: int, total: int) -> None: self.events.put(("progress", (received, total)))
        def status(stage: str) -> None: self.events.put(("status", stage))
        def worker() -> None:
            try:
                try:
                    installer = download_update(self.release, progress=progress, cancel_event=self.cancel_event, status=status)
                except TypeError as error:
                    # Keep test/distro adapters written for the older callback-only
                    # downloader usable while the production implementation gains
                    # cancellation and phase reporting.
                    if "unexpected keyword argument" not in str(error):
                        raise
                    installer = download_update(self.release, progress=progress)
                self.events.put(("ready", installer))
            except UpdateCancelled:
                self.events.put(("cancelled", None))
            except UpdateError as error:
                self.events.put(("error", str(error)))
        threading.Thread(target=worker, name="update-download", daemon=True).start()
        self.window.after(50, self._poll)

    def cancel_download(self) -> None:
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status.configure(text=self._txt("Cancelling download…", "Ruším stahování…"))

    def _restore_controls(self) -> None:
        for button in (self.install_button, self.skip_button, self.ask_button): button.configure(state="normal")
        self.cancel_button.pack_forget(); self.cancel_button.configure(state="normal")

    def show_install_launch_error(self, message: str) -> None:
        """Keep the dialog usable when Windows rejects the installer launch."""
        self.status.configure(text=message, style="Warning.TLabel")
        self.progress.pack_forget()
        self.progress_detail.pack_forget()
        self._restore_controls()

    @staticmethod
    def _duration(seconds: float, czech: bool) -> str:
        seconds = max(1, int(round(seconds)))
        if seconds >= 60:
            minutes, seconds = divmod(seconds, 60)
            return f"{minutes} min {seconds} s" if czech else f"{minutes} min, {seconds} sec"
        return f"{seconds} s" if czech else f"{seconds} sec"

    def _render_transfer(self, received: int, total: int) -> None:
        # The overall update is not complete until checksum verification and
        # installer preparation succeed, so downloaded bytes top out at 99%.
        self.progress.configure(value=min(99.0, (received / max(1, total)) * 100))
        self.status.configure(text=self._txt(f"Downloading… {received / 1024**2:.1f} of {total / 1024**2:.1f} MB", f"Stahuji… {received / 1024**2:.1f} z {total / 1024**2:.1f} MB"))
        now = time.monotonic()
        if self._last_sample is not None:
            elapsed = now - self._last_sample[0]
            if elapsed > 0:
                sample = max(0.0, (received - self._last_sample[1]) / elapsed)
                self._rate_bytes_per_second = sample if self._rate_bytes_per_second is None else .25 * sample + .75 * self._rate_bytes_per_second
        self._last_sample = (now, received)
        filename = Path(urlparse(self.release.installer_url).path).name
        detail = self._txt(f"File: {filename}", f"Soubor: {filename}")
        if now - self._download_started >= 2.0 and self._rate_bytes_per_second and self._rate_bytes_per_second > 0:
            rate = self._rate_bytes_per_second / 1024**2
            remaining = max(0, total - received) / self._rate_bytes_per_second
            detail += self._txt(f" · Speed: {rate:.1f} MB/s · Time remaining: {self._duration(remaining, False)}", f" · Rychlost: {rate:.1f} MB/s · Zbývá: {self._duration(remaining, True)}")
        self.progress_detail.configure(text=detail)

    def _poll(self) -> None:
        keep_polling = True
        while True:
            try: event, value = self.events.get_nowait()
            except queue.Empty: break
            if event == "progress":
                received, total = value  # type: ignore[misc]
                self._render_transfer(received, total)
            elif event == "status":
                if value == "verifying": self.status.configure(text=self._txt("Verifying checksum…", "Ověřuji kontrolní součet…"))
                elif value == "preparing": self.status.configure(text=self._txt("Preparing installation…", "Připravuji instalaci…"))
            elif event == "ready":
                keep_polling = False
                self.progress.configure(value=100)
                self.status.configure(text=self._txt("Verified · preparing installation…", "Ověřeno · připravuji instalaci…"))
                self.on_install_ready(value)  # type: ignore[arg-type]
            elif event == "cancelled":
                keep_polling = False
                self.status.configure(text=self._txt("Download cancelled. No partial file was kept.", "Stahování zrušeno. Částečný soubor nebyl zachován."))
                self.progress.pack_forget(); self.progress_detail.pack_forget(); self._restore_controls()
            elif event == "error":
                keep_polling = False
                self.status.configure(text=str(value), style="Warning.TLabel"); self._restore_controls()
        if keep_polling and self.window.winfo_exists(): self.window.after(80, self._poll)
