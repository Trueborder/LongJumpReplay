import tkinter as tk

from src.config import AppConfig
from src.settings_dialog import SettingsDialog


def test_category_settings_dialog_builds_all_pages():
    root = tk.Tk(); root.withdraw(); applied = []
    dialog = SettingsDialog(root, AppConfig(), applied.append)
    dialog.update_idletasks()
    assert set(dialog._pages) == {
        "general", "appearance", "performance", "camera", "board", "competition",
        "rounds", "decisions", "final", "replay", "views", "assist",
        "hotkeys", "shuttle", "recovery", "advanced",
    }
    assert dialog._vars["athlete_timer_duration"].get() == 60
    assert dialog.hotkey_tree.set("timer_toggle", "key") == ""
    assert set(dialog._nav_group_labels) == {"essentials", "judging", "replay", "system"}
    assert dialog._nav_buttons["general"].cget("style") == "SettingsNav.TButton"
    dialog._show_page("competition")
    assert dialog._current_page == "competition"
    assert dialog.roster_tree is not None
    for page in dialog._pages:
        dialog._show_page(page); dialog.update_idletasks()
        assert dialog.apply_button.winfo_manager() == "pack"
        assert dialog.apply_close_button.winfo_manager() == "pack"
        assert dialog.footer.winfo_manager() == "grid"
        assert dialog._nav_buttons[page].instate(["selected"])
    dialog.destroy(); root.destroy()
