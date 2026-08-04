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
    dialog._load_low_resource_mode()
    assert dialog._vars["preview_hz"].get() == 20
    assert dialog._vars["store_nth"].get() == 2
    assert dialog._vars["buffer_memory"].get() == 1024
    assert dialog.hotkey_tree.set("timer_toggle", "key") == ""
    assert set(dialog._nav_group_labels) == {"essentials", "judging", "replay", "system"}
    assert dialog._nav_buttons["general"].cget("style") == "SettingsNav.TButton"
    general_inner = dialog._page_inners["general"]
    general_rows = [(card, widget, desc) for card, widget, desc in dialog._setting_rows if card.master is general_inner]
    dialog._show_page("general"); dialog.update_idletasks()
    assert len({widget.winfo_x() for _card, widget, _desc in general_rows}) == 1
    assert all(widget.winfo_x() >= 500 for _card, widget, _desc in general_rows)
    described = [desc for _card, _widget, desc in general_rows if desc is not None]
    assert len({desc.winfo_x() for desc in described}) == 1
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
