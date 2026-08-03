import tkinter as tk
from tkinter import ttk

from src.hotkeys import HotkeyRouter


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
    router.close(); root.destroy()
