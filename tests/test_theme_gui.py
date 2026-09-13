import tkinter as tk
from tkinter import ttk

import pytest

from src.theme import (
    BUTTON_STYLES,
    ThemeManager,
    _popup_is_fullscreen,
    _win32_window_and_monitor_rects,
    bind_resize_only,
    button_style,
    configure_popup,
)


class _FullscreenValue:
    def __init__(self, value: object) -> None:
        self.value = value

    def attributes(self, _name: str) -> object:
        return self.value


class _BindableWidget:
    def __init__(self) -> None:
        self.handler = None

    def bind(self, _sequence: str, handler, add: str = "") -> str:
        self.handler = handler
        assert add == "+"
        return "resize-binding"

    def winfo_width(self) -> int:
        return 100

    def winfo_height(self) -> int:
        return 50


def test_resize_binding_ignores_position_only_configure_events() -> None:
    widget = _BindableWidget()
    calls: list[tuple[int, int]] = []
    bind_resize_only(widget, lambda event: calls.append((event.width, event.height)))

    class Event:
        width = 100
        height = 50

    assert widget.handler is not None
    widget.handler(Event())
    widget.handler(Event())
    Event.width = 101
    widget.handler(Event())
    assert calls == [(100, 50), (101, 50)]


def test_fullscreen_string_zero_does_not_disable_popup_centering() -> None:
    assert _popup_is_fullscreen(_FullscreenValue("0")) is False  # type: ignore[arg-type]
    assert _popup_is_fullscreen(_FullscreenValue("1")) is True  # type: ignore[arg-type]


def test_button_variant_names_are_centralized() -> None:
    assert button_style("secondary") == "Secondary.TButton"
    assert button_style("PRIMARY") == "Primary.TButton"
    assert button_style("destructive") == "Destructive.TButton"
    with pytest.raises(ValueError):
        button_style("unknown")


@pytest.mark.parametrize("theme_name", ["dark", "light"])
def test_button_system_has_stable_sizes_and_states(theme_name: str) -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        manager = ThemeManager(root)
        palette = manager.apply(theme_name)
        style = ttk.Style(root)
        for style_name in BUTTON_STYLES.values():
            assert style.layout(style_name)
        menu_layout = str(style.layout("TMenubutton"))
        expected_menu_element = f"Modern{theme_name.title()}.menu.Menubutton.background"
        assert expected_menu_element in menu_layout
        assert "Menubutton.label" in menu_layout
        assert "Menubutton.indicator" in menu_layout

        standard = ttk.Button(root, text="Open recording", style=button_style("secondary"))
        judge_buttons = [
            ttk.Button(root, text=label, style=button_style(variant))
            for label, variant in (("PENDING", "pending"), ("VALID", "valid"), ("FOUL", "foul"), ("REVIEW", "review"))
        ]
        root.update_idletasks()
        assert 30 <= standard.winfo_reqheight() <= 36
        assert len({button.winfo_reqheight() for button in judge_buttons}) == 1
        assert 32 <= judge_buttons[0].winfo_reqheight() <= 38

        judge_buttons[1].state(["selected"])
        assert judge_buttons[1].instate(["selected"])
        standard.state(["disabled"])
        assert standard.instate(["disabled"])
        assert style.lookup(button_style("secondary"), "foreground", ("disabled",)) == palette["button_disabled_text"]
        assert style.lookup(button_style("secondary"), "background", ("active",)) == palette["bg"]
        assert manager._image_assets[f"Modern{theme_name.title()}.primary.normal"].transparency_get(0, 0)
    finally:
        root.destroy()


def test_configure_popup_centers_final_geometry_on_screen() -> None:
    root = tk.Tk()
    root.geometry("900x650+80+60")
    root.update_idletasks()
    root.update()
    popup = tk.Toplevel(root)
    try:
        configure_popup(popup, root)
        popup.geometry("320x180")
        root.update_idletasks()
        root.update()

        measured = _win32_window_and_monitor_rects(popup, root)
        if measured is not None:
            popup_rect, screen_rect = measured
            assert abs((popup_rect[0] + popup_rect[2]) - (screen_rect[0] + screen_rect[2])) <= 2
            assert abs((popup_rect[1] + popup_rect[3]) - (screen_rect[1] + screen_rect[3])) <= 2
        else:
            expected_x = (popup.winfo_screenwidth() - popup.winfo_width()) // 2
            expected_y = (popup.winfo_screenheight() - popup.winfo_height()) // 2
            assert abs(popup.winfo_x() - expected_x) <= 2
            assert abs(popup.winfo_y() - expected_y) <= 2
    finally:
        popup.destroy()
        root.destroy()
