from __future__ import annotations

import hashlib
from pathlib import Path
import time
import tkinter as tk

from src.theme import ThemeManager
from src.update_ui import UpdateDialog
from src.updater import ReleaseInfo


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

    def fake_download(_release, *, progress):
        progress(9, 9)
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
