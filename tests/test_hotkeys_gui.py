from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

from src import hotkeys
from src.hotkeys import HotkeyRouter


def test_event_to_hotkey_uses_windows_alt_mask(monkeypatch):
    monkeypatch.setattr(hotkeys.sys, "platform", "win32")

    assert hotkeys.event_to_hotkey(SimpleNamespace(state=0x0008, keysym="v")) == "v"
    assert hotkeys.event_to_hotkey(SimpleNamespace(state=0x20000, keysym="v")) == "Alt-v"
    assert hotkeys.event_to_hotkey(SimpleNamespace(state=0x20005, keysym="v")) == "Control-Shift-Alt-v"


def test_event_to_hotkey_keeps_x11_alt_mask(monkeypatch):
    monkeypatch.setattr(hotkeys.sys, "platform", "linux")

    assert hotkeys.event_to_hotkey(SimpleNamespace(state=0x0008, keysym="v")) == "Alt-v"


def test_space_beats_focused_button():
    root = tk.Tk()
    clicks = []
    freezes = []
    button = ttk.Button(root, text='Other button', command=lambda: clicks.append(1))
    button.pack()
    root.update()
    button.focus_force()
    router = HotkeyRouter(root)
    router.attach_tree()
    router.install({'freeze_toggle': 'space'}, {'freeze_toggle': lambda: freezes.append(1)})
    root.event_generate('<KeyPress-space>')
    root.update()
    root.event_generate('<KeyRelease-space>')
    root.update()
    assert freezes == [1]
    assert clicks == []
    frames = []
    overridden = []

    def override(event):
        if event.keysym in {"Right", "Up", "Return"}:
            overridden.append(event.keysym)
            return True
        return False

    router.install(
        {"next_frame": "Right", "freeze_toggle": "space"},
        {"next_frame": lambda: frames.append(1), "freeze_toggle": lambda: freezes.append(1)},
        key_override=override,
    )
    for sequence in ("<KeyPress-Right>", "<KeyPress-Up>", "<KeyPress-Return>"):
        button.event_generate(sequence); root.update()
    button.event_generate("<KeyPress-space>"); root.update()
    button.event_generate("<KeyRelease-space>"); root.update()

    assert overridden == ["Right", "Up", "Return"]
    assert frames == []
    assert freezes == [1, 1]
    router.close(); root.destroy()
