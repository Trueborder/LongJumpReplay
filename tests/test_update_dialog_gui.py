from __future__ import annotations

import hashlib
from pathlib import Path
import threading
import time
import tkinter as tk

from src.theme import ThemeManager, show_themed_info
from src.update_ui import UpdateCheckDialog, UpdateDialog
from src.updater import ReleaseInfo
from src.updater import UpdateCancelled


def release() -> ReleaseInfo:
    content = b"installer"
    return ReleaseInfo(
        version="3.3.1",
        published_at="2026-08-19T12:00:00Z",
        installer_url="https://files.tomaspisar.cz/releases/3.3.1/LongJumpReplay-Setup-3.3.1.exe",
        sha256=hashlib.sha256(content).hexdigest().upper(),
        size=len(content),
        notes=("Update dialog test",),
    )


def test_update_check_uses_one_indeterminate_bar_until_closed():
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    settings = tk.Toplevel(root); settings.grab_set()
    dialog = UpdateCheckDialog(settings, "en")
    try:
        assert str(dialog.progress.cget("mode")) == "indeterminate"
        assert dialog.progress.winfo_manager() == "pack"
        assert str(root.grab_current()) == str(dialog.window)
    finally:
        dialog.close(); settings.destroy(); root.destroy()


def test_update_dialog_has_all_customer_choices(monkeypatch, tmp_path):
    root = tk.Tk()
    root.withdraw()
    ThemeManager(root).apply("dark")
    skipped = []
    monkeypatch.setattr("src.update_ui.skip_version", lambda version: skipped.append(version))
    dialog = UpdateDialog(root, release(), "en", lambda _path: None)
    dialog.window.update_idletasks()
    assert dialog.install_button.cget("text") == "Install"
    assert dialog.skip_button.cget("text") == "Skip this version"
    assert dialog.ask_button.cget("text") == "Ask later"
    dialog.skip()
    assert skipped == ["3.3.1"]
    root.destroy()


def test_update_dialog_reports_download_and_hands_off(monkeypatch, tmp_path):
    root = tk.Tk()
    root.withdraw()
    ThemeManager(root).apply("light")
    installer = tmp_path / "LongJumpReplay-Setup-3.3.1.exe"
    installer.write_bytes(b"installer")
    delivered: list[Path] = []

    def fake_download(_release, *, progress, cancel_event, status):
        assert not cancel_event.is_set()
        status("downloading")
        progress(9, 9)
        status("verifying")
        status("preparing")
        return installer

    monkeypatch.setattr("src.update_ui.download_update", fake_download)
    dialog = UpdateDialog(root, release(), "cs", delivered.append)
    dialog.install()
    deadline = 100
    while not delivered and deadline:
        root.update()
        time.sleep(0.01)
        deadline -= 1
    assert delivered == [installer]
    dialog.ask_later()
    root.destroy()


def test_update_dialog_cancel_restores_customer_controls(monkeypatch):
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    entered = threading.Event()

    def fake_download(_release, *, progress, cancel_event, status):
        status("downloading"); progress(1, 9); entered.set()
        cancel_event.wait(timeout=2)
        raise UpdateCancelled("cancelled")

    monkeypatch.setattr("src.update_ui.download_update", fake_download)
    dialog = UpdateDialog(root, release(), "en", lambda _path: None)
    dialog.install()
    deadline = time.monotonic() + 2
    while not entered.is_set() and time.monotonic() < deadline:
        root.update(); time.sleep(.01)
    dialog.cancel_download()
    while dialog.install_button.instate(["disabled"]) and time.monotonic() < deadline:
        root.update(); time.sleep(.01)
    assert dialog.install_button.instate(["!disabled"])
    assert dialog.skip_button.instate(["!disabled"])
    assert dialog.ask_button.instate(["!disabled"])
    assert not dialog.cancel_button.winfo_manager()
    dialog.ask_later(); root.destroy()


def test_update_dialog_restores_settings_grab_when_closed():
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    settings = tk.Toplevel(root)
    settings.grab_set()
    dialog = UpdateDialog(settings, release(), "en", lambda _path: None)
    assert str(root.grab_current()) == str(dialog.window)

    dialog.ask_later()
    assert str(root.grab_current()) == str(settings)

    settings.destroy(); root.destroy()


def test_current_version_message_restores_settings_grab():
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    settings = tk.Toplevel(root)
    settings.grab_set()

    def close_message() -> None:
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        message = next(child for child in descendants(root) if isinstance(child, tk.Toplevel) and child is not settings)
        button = next(widget for widget in descendants(message) if isinstance(widget, ttk.Button))
        button.invoke()

    from tkinter import ttk
    root.after(50, close_message)
    show_themed_info(settings, "Update", "LongJumpReplay is up to date.")
    assert str(root.grab_current()) == str(settings)

    settings.destroy(); root.destroy()
