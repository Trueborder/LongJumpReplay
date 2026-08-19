"""Non-blocking themed Tk interface for application updates."""

from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .theme import configure_popup
from .updater import ReleaseInfo, UpdateError, download_update, skip_version


class UpdateDialog:
    def __init__(
        self,
        parent: tk.Misc,
        release: ReleaseInfo,
        language: str,
        on_install_ready: Callable[[Path], None],
    ) -> None:
        self.parent = parent
        self.release = release
        self.language = language
        self.on_install_ready = on_install_ready
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.window = tk.Toplevel(parent)
        self.palette = configure_popup(self.window, parent)
        self.window.title(self._txt("LongJumpReplay update", "Aktualizace LongJumpReplay"))
        self.window.geometry("590x430")
        self.window.minsize(540, 390)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.ask_later)

        body = ttk.Frame(self.window, style="Dialog.TFrame", padding=(24, 22))
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=self._txt("UPDATE AVAILABLE", "DOSTUPNÁ AKTUALIZACE"),
            style="ContextTitle.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=self._txt(
                f"LongJumpReplay {release.version} is ready",
                f"LongJumpReplay {release.version} je připraven",
            ),
            style="DialogTitle.TLabel",
        ).pack(anchor="w", pady=(5, 8))
        size_mb = release.size / (1024 * 1024)
        ttk.Label(
            body,
            text=self._txt(
                f"Installed version can be updated in one step · {size_mb:.1f} MB",
                f"Nainstalovanou verzi lze aktualizovat v jednom kroku · {size_mb:.1f} MB",
            ),
            style="DialogBody.TLabel",
        ).pack(anchor="w")

        notes_frame = ttk.Frame(body, style="Panel.TFrame", padding=(14, 12))
        notes_frame.pack(fill="both", expand=True, pady=(16, 14))
        ttk.Label(
            notes_frame,
            text=self._txt("WHAT'S NEW", "CO JE NOVÉHO"),
            style="ContextTitle.TLabel",
        ).pack(anchor="w")
        notes = release.notes or (
            self._txt("Reliability and application improvements.", "Vylepšení spolehlivosti a aplikace."),
        )
        ttk.Label(
            notes_frame,
            text="\n".join(f"• {item}" for item in notes),
            style="Text.TLabel",
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self.status = ttk.Label(body, text="", style="Muted.TLabel")
        self.status.pack(anchor="w")
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)

        self.footer = ttk.Frame(body, style="Dialog.TFrame")
        self.footer.pack(fill="x", pady=(14, 0))
        self.ask_button = ttk.Button(
            self.footer,
            text=self._txt("Ask later", "Připomenout příště"),
            style="Control.TButton",
            command=self.ask_later,
        )
        self.ask_button.pack(side="left")
        self.skip_button = ttk.Button(
            self.footer,
            text=self._txt("Skip this version", "Přeskočit tuto verzi"),
            style="Control.TButton",
            command=self.skip,
        )
        self.skip_button.pack(side="right", padx=(8, 0))
        self.install_button = ttk.Button(
            self.footer,
            text=self._txt("Install", "Nainstalovat"),
            style="Accent.TButton",
            command=self.install,
        )
        self.install_button.pack(side="right", padx=(8, 0))
        self.window.grab_set()

    def _txt(self, english: str, czech: str) -> str:
        return czech if self.language == "cs" else english

    def ask_later(self) -> None:
        try:
            self.window.grab_release()
            self.window.destroy()
        except tk.TclError:
            pass

    def skip(self) -> None:
        skip_version(self.release.version)
        self.ask_later()

    def install(self) -> None:
        self.install_button.configure(state="disabled")
        self.skip_button.configure(state="disabled")
        self.ask_button.configure(state="disabled")
        self.status.configure(text=self._txt("Downloading verified update…", "Stahuji ověřenou aktualizaci…"))
        self.progress.pack(fill="x", before=self.footer, pady=(12, 0))

        def progress(received: int, total: int) -> None:
            self.events.put(("progress", (received, total)))

        def worker() -> None:
            try:
                installer = download_update(self.release, progress=progress)
                self.events.put(("ready", installer))
            except UpdateError as error:
                self.events.put(("error", str(error)))

        threading.Thread(target=worker, name="update-download", daemon=True).start()
        self.window.after(50, self._poll)

    def _poll(self) -> None:
        keep_polling = True
        while True:
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "progress":
                received, total = value  # type: ignore[misc]
                self.progress.configure(value=(received / max(1, total)) * 100)
                self.status.configure(
                    text=self._txt(
                        f"Downloading… {received / 1024**2:.1f} of {total / 1024**2:.1f} MB",
                        f"Stahuji… {received / 1024**2:.1f} z {total / 1024**2:.1f} MB",
                    )
                )
            elif event == "ready":
                keep_polling = False
                self.status.configure(text=self._txt("Verified · preparing installation…", "Ověřeno · připravuji instalaci…"))
                self.on_install_ready(value)  # type: ignore[arg-type]
            elif event == "error":
                keep_polling = False
                self.status.configure(text=str(value), style="Warning.TLabel")
                self.install_button.configure(state="normal")
                self.skip_button.configure(state="normal")
                self.ask_button.configure(state="normal")
        if keep_polling and self.window.winfo_exists():
            self.window.after(80, self._poll)
