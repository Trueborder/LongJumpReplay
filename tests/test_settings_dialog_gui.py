import tkinter as tk
from tkinter import ttk

from src.config import AppConfig
from src.camera_devices import CameraDevice
from src.settings_dialog import SettingsDialog
from src.theme import ThemeManager


def test_category_settings_dialog_builds_all_pages(monkeypatch):
    monkeypatch.setattr(
        "src.settings_dialog.enumerate_camera_devices",
        lambda current: [CameraDevice(0, "Lenovo Built-in"), CameraDevice(1, "OBS Virtual Camera")],
    )
    root = tk.Tk(); root.withdraw(); theme_manager = ThemeManager(root); theme_manager.apply("dark"); applied = []
    dialog = SettingsDialog(root, AppConfig(), applied.append)
    dialog.update_idletasks()
    style = ttk.Style(dialog)
    assert "Modern" in str(style.layout("TCheckbutton"))
    assert "ModernDark.neutral.Button.background" in str(style.layout("TButton"))
    assert "ModernDark.Combo.field" in str(style.layout("TCombobox"))
    assert theme_manager._image_assets["ModernDark.neutral.normal"].height() == 20
    assert int(style.lookup("TCombobox", "arrowsize")) == 15
    assert tuple(style.lookup("TCombobox", "padding")) == (9, 0)
    checked_image = theme_manager._image_assets["ModernDark.checked"]
    unchecked_image = theme_manager._image_assets["ModernDark.unchecked"]
    assert checked_image.get(11, 11) != unchecked_image.get(11, 11)
    first_checkbox = next(widget for _card, widget, _desc in dialog._setting_rows if isinstance(widget, ttk.Checkbutton))
    assert first_checkbox.instate(["selected"])
    first_checkbox.invoke(); dialog.update_idletasks()
    assert first_checkbox.instate(["!selected"])
    theme_manager.apply("light")
    assert "ModernLight" in str(style.layout("TCheckbutton"))
    assert "ModernLight.neutral.Button.background" in str(style.layout("TButton"))
    assert set(dialog._pages) == {
        "general", "appearance", "performance", "camera", "board", "competition",
        "rounds", "decisions", "final", "replay", "views", "assist",
        "hotkeys", "shuttle", "recovery", "advanced",
    }
    assert dialog._vars["athlete_timer_duration"].get() == 60
    assert str(dialog.camera_device_combo.cget("state")) == "readonly"
    assert tuple(dialog.camera_device_combo.cget("values")) == ("0 · Lenovo Built-in", "1 · OBS Virtual Camera")
    dialog._vars["camera_device_choice"].set("1 · OBS Virtual Camera")
    assert dialog._vars["device"].get() == 1
    dialog._load_low_resource_mode()
    assert dialog._vars["preview_hz"].get() == 20
    assert dialog._vars["store_nth"].get() == 2
    assert dialog._vars["buffer_memory"].get() == 1024
    assert dialog.hotkey_tree.set("timer_toggle", "key") == ""
    assert set(dialog._nav_group_labels) == {"essentials", "judging", "replay", "system"}
    assert dialog._nav_buttons["general"].cget("style") == "SettingsNav.TButton"
    assert dialog._nav_buttons["general"].winfo_reqheight() <= 36
    assert dialog.nav_scrollbar.winfo_manager() == "grid"
    assert dialog.nav_canvas.cget("yscrollcommand")
    assert dialog.nav_canvas.bbox("all") is not None
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
