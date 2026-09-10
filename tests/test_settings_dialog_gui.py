import tkinter as tk
from tkinter import ttk
import math

from src.config import AppConfig
from src.camera_devices import CameraDevice
from src.settings_dialog import SettingsDialog
from src.theme import COMPACT_UI_RATIO, ThemeManager


def test_category_settings_dialog_builds_all_pages(monkeypatch):
    monkeypatch.setattr(
        "src.settings_dialog.enumerate_camera_devices",
        lambda current: [CameraDevice(0, "Lenovo Built-in"), CameraDevice(1, "OBS Virtual Camera")],
    )
    root = tk.Tk(); root.withdraw()
    native_scaling = float(root.tk.call("tk", "scaling"))
    theme_manager = ThemeManager(root); theme_manager.apply("dark"); applied = []
    dialog = SettingsDialog(root, AppConfig(), applied.append)
    dialog.update_idletasks()
    style = ttk.Style(dialog)
    assert "Modern" in str(style.layout("TCheckbutton"))
    assert "ModernDark.neutral.Button.background" not in str(style.layout("TButton"))
    assert "ModernDark.Combo.field" not in str(style.layout("TCombobox"))
    assert "Combobox.downarrow" in str(style.layout("TCombobox"))
    assert theme_manager._image_assets["ModernDark.neutral.normal"].height() == 22
    assert math.isclose(theme_manager.tk_scaling, max(1.0, native_scaling * COMPACT_UI_RATIO), rel_tol=.01)
    assert math.isclose(float(root.tk.call("tk", "scaling")), theme_manager.tk_scaling, rel_tol=.01)
    assert int(style.lookup("TCombobox", "arrowsize")) == 12
    assert tuple(style.lookup("TCombobox", "padding")) == (7, 0)
    assert int(style.lookup("Treeview", "rowheight")) == 19
    assert tuple(style.lookup("Control.TButton", "padding")) == (7, 0)
    assert str(style.lookup("Control.TButton", "font")) == "{Segoe UI} 9"
    checked_image = theme_manager._image_assets["ModernDark.checked"]
    unchecked_image = theme_manager._image_assets["ModernDark.unchecked"]
    assert checked_image.height() == unchecked_image.height() == 16
    assert checked_image.get(8, 9) != unchecked_image.get(8, 9)
    first_checkbox = next(widget for _card, widget, _desc in dialog._setting_rows if isinstance(widget, ttk.Checkbutton))
    assert first_checkbox.instate(["selected"])
    first_checkbox.invoke(); dialog.update_idletasks()
    assert first_checkbox.instate(["!selected"])
    theme_manager.apply("light")
    assert math.isclose(float(root.tk.call("tk", "scaling")), theme_manager.tk_scaling, rel_tol=.01)
    assert "ModernLight" in str(style.layout("TCheckbutton"))
    assert "ModernLight.neutral.Button.background" not in str(style.layout("TButton"))
    assert set(dialog._pages) == {
        "general", "camera_recording", "competition", "judging",
        "board_assist", "workspace_controls", "licence", "advanced",
    }
    assert dialog._vars["athlete_timer_duration"].get() == 60
    assert str(dialog.camera_device_combo.cget("state")) == "readonly"
    assert str(dialog.camera_file_entry.cget("state")) == "disabled"
    assert dialog.camera_file_browse_button.instate(["disabled"])
    source_combos = [widget for _card, widget, _desc in dialog._setting_rows if isinstance(widget, ttk.Combobox) and "camera" in tuple(widget.cget("values"))]
    assert source_combos and "synthetic" not in tuple(source_combos[0].cget("values"))
    assert tuple(dialog.camera_device_combo.cget("values")) == ("0 · Lenovo Built-in", "1 · OBS Virtual Camera")
    dialog._vars["camera_device_choice"].set("1 · OBS Virtual Camera")
    assert dialog._vars["device"].get() == 1
    dialog._load_low_resource_mode()
    assert dialog._vars["preview_hz"].get() == 20
    assert dialog._vars["store_nth"].get() == 2
    assert dialog._vars["buffer_memory"].get() == 1024
    assert dialog.hotkey_tree.set("timer_toggle", "key") == ""
    assert set(dialog._nav_group_labels) == {"essentials", "event", "system"}
    assert dialog._nav_buttons["general"].cget("style") == "SettingsNav.TButton"
    assert dialog._nav_buttons["general"].winfo_reqheight() <= 36
    assert dialog.nav_scrollbar.winfo_manager() == "grid"
    assert dialog.nav_canvas.cget("yscrollcommand")
    assert dialog.nav_canvas.bbox("all") is not None
    general_rows = [
        (entry["card"], entry["widget"], next(desc for card, _widget, desc in dialog._setting_rows if card is entry["card"]))
        for entry in dialog._search_entries if entry["page"] == "general"
    ]
    dialog._show_page("general"); dialog.update_idletasks()
    assert len({widget.winfo_x() for _card, widget, _desc in general_rows}) == 1
    assert all(widget.winfo_x() >= 500 for _card, widget, _desc in general_rows)
    described = [desc for _card, _widget, desc in general_rows if desc is not None]
    assert len(described) == len(general_rows)
    assert len({desc.winfo_x() for desc in described}) == 1
    dialog._vars["show_tooltips"].set(False); dialog.update_idletasks()
    assert all(not desc.winfo_manager() for desc in described)
    assert all(not header.winfo_manager() for _columns, header in dialog._description_headers)
    dialog._vars["show_tooltips"].set(True); dialog.update_idletasks()
    assert all(desc.winfo_manager() == "grid" for desc in described)
    dialog._show_page("competition")
    assert dialog._current_page == "competition"
    assert dialog.roster_tree is not None
    for page in dialog._pages:
        dialog._show_page(page); dialog.update_idletasks()
        assert dialog.apply_button.winfo_manager() == "pack"
        assert dialog.apply_close_button.winfo_manager() == "pack"
        assert dialog.footer.winfo_manager() == "grid"
        assert dialog._nav_buttons[page].instate(["selected"])
    dialog._dirty = False
    dialog.search_var.set("FOURCC"); dialog.update_idletasks()
    assert not dialog._dirty
    assert dialog.search_results.winfo_manager() == "pack"
    assert len(dialog.search_results_tree.get_children()) == 1
    dialog._open_selected_search_result(); dialog.update_idletasks()
    assert dialog._current_page == "advanced"
    assert dialog.search_var.get() == ""
    dialog.search_var.set("version"); dialog.update_idletasks()
    assert any(dialog.search_results_tree.set(item, "setting") == "Application version" for item in dialog.search_results_tree.get_children())
    dialog._open_selected_search_result(); dialog.update_idletasks()
    assert dialog._current_page == "licence"
    assert not dialog._dirty
    dialog.destroy(); root.destroy()


def test_camera_file_source_can_be_typed_or_chosen(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.settings_dialog.enumerate_camera_devices",
        lambda current: [CameraDevice(current, "Current camera")],
    )
    chosen = tmp_path / "jump replay.mp4"
    monkeypatch.setattr("src.settings_dialog.filedialog.askopenfilename", lambda **_kwargs: str(chosen))
    root = tk.Tk(); root.geometry("2x2+0+0"); ThemeManager(root).apply("dark")
    config = AppConfig(); config.general.language = "cs"
    dialog = SettingsDialog(root, config, lambda _updated: None)
    dialog.geometry("1100x700"); dialog._show_page("camera_recording"); dialog.update()
    assert dialog.camera_file_browse_button.winfo_rootx() + dialog.camera_file_browse_button.winfo_width() <= dialog.page_host.winfo_rootx() + dialog.page_host.winfo_width()

    dialog._vars["source"].set("file")
    assert str(dialog.camera_device_combo.cget("state")) == "disabled"
    assert str(dialog.camera_file_entry.cget("state")) == "normal"
    assert dialog.camera_file_browse_button.instate(["!disabled"])

    dialog.camera_file_browse_button.invoke()
    assert dialog._vars["file_path"].get() == str(chosen)
    updated = dialog._apply_vars()
    assert updated.camera.source_type == "file"
    assert updated.camera.file_path == str(chosen)

    dialog.destroy(); root.destroy()


def test_settings_repairs_invalid_runtime_panel_measurements(monkeypatch):
    monkeypatch.setattr(
        "src.settings_dialog.enumerate_camera_devices",
        lambda current: [CameraDevice(current, "Current camera")],
    )
    config = AppConfig()
    config.display.attempts_panel_width = 1
    config.display.timeline_height = 900
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    dialog = SettingsDialog(root, config, lambda _updated: None)

    assert "attempts_width" not in dialog._vars
    assert "timeline_height" not in dialog._vars
    dialog._apply_vars().validate()

    dialog.destroy(); root.destroy()


def test_settings_can_start_manual_update_check(monkeypatch):
    monkeypatch.setattr(
        "src.settings_dialog.enumerate_camera_devices",
        lambda current: [CameraDevice(current, "Current camera")],
    )
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    requested_from = []
    dialog = SettingsDialog(
        root,
        AppConfig(),
        lambda _updated: None,
        on_check_updates=requested_from.append,
    )

    assert dialog.check_updates_button.cget("text") == "Check for updates…"
    assert dialog.check_updates_button.instate(["!disabled"])
    dialog.check_updates_button.invoke()
    assert requested_from == [dialog]

    dialog.destroy(); root.destroy()


def test_licence_page_shows_diagnostics_and_copies_safe_summary(monkeypatch):
    monkeypatch.setattr(
        "src.settings_dialog.enumerate_camera_devices",
        lambda current: [CameraDevice(current, "Current camera")],
    )
    monkeypatch.setattr(
        "src.activation.authorization_details",
        lambda: (True, "authorization.accepted", {
            "license_type": "lifetime", "expires_at": 1_900_000_000,
            "max_devices": 2, "machine_id": "must-not-be-copied",
        }, 1_800_000_000),
    )
    monkeypatch.setattr(
        "src.trial.trial_status",
        lambda: __import__("src.trial", fromlist=["TrialStatus"]).TrialStatus(True, False, 1, 2, 1_900_000_000),
    )
    monkeypatch.setattr("src.settings_dialog.show_themed_info", lambda *args: None)
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    dialog = SettingsDialog(root, AppConfig(), lambda _updated: None)
    dialog._copy_support_summary()
    summary = dialog.clipboard_get()
    assert "6.2.4" in summary
    assert "lifetime" in summary
    assert "must-not-be-copied" not in summary
    assert "machine_id" not in summary
    assert dialog.copy_support_button.instate(["!disabled"])
    dialog.destroy(); root.destroy()
