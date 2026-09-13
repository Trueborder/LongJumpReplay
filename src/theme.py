from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk
import ctypes
from ctypes import wintypes
from collections.abc import Callable


# The original interface was laid out at approximately 130% of the density the
# operator now wants. Keep Windows' native DPI factor, but render application
# typography and character-sized controls at roughly 100 / 130 of that size.
COMPACT_UI_RATIO = 100.0 / 130.0
MIN_COMPACT_TK_SCALING = 1.0
BUTTON_CORNER_RADIUS = 6


def apply_compact_ui_scaling(root: tk.Misc) -> float:
    """Apply the compact density once without compounding on theme changes."""
    native = getattr(root, "_ljr_native_tk_scaling", None)
    if native is None:
        try:
            native = float(root.tk.call("tk", "scaling"))
        except (tk.TclError, TypeError, ValueError):
            native = 1.0
        root._ljr_native_tk_scaling = native
    target = max(MIN_COMPACT_TK_SCALING, float(native) * COMPACT_UI_RATIO)
    try:
        root.tk.call("tk", "scaling", target)
    except tk.TclError:
        pass
    root._ljr_compact_tk_scaling = target
    return target


DARK = {
    "bg": "#090d14", "surface": "#111722", "surface2": "#182131", "border": "#2a374a",
    "text": "#f4f7fb", "muted": "#96a4b8", "accent": "#4f8cff", "accent_hover": "#78a8ff",
    "live": "#35d39a", "warning": "#f5bd4f", "danger": "#ff6675", "video": "#03060a",
    "timeline": "#0d1420", "tick": "#71839c", "selection": "#254c80",
    "recorded": "#326fc4", "assist": "#8b6de3", "prediction": "#f5bd4f", "playhead": "#f4f7fb",
    "valid_soft": "#12392d", "foul_soft": "#47212a", "review_soft": "#493918", "pending_soft": "#1c293b",
    "button_bg": "#182131", "button_hover": "#203149", "button_pressed": "#142033",
    "button_border": "#344761", "button_border_hover": "#5c7fa8",
    "button_disabled_bg": "#111722", "button_disabled_border": "#263143", "button_disabled_text": "#66758a",
    "primary_pressed": "#386fc9", "success_hover": "#50dda9", "success_pressed": "#259970",
    "danger_hover": "#ff8290", "danger_pressed": "#c94a59", "warning_hover": "#ffd16f", "warning_pressed": "#c7922f",
    "neutral_bg": "#303b4c", "neutral_hover": "#3b4960", "neutral_pressed": "#252f3e",
}
LIGHT = {
    "bg": "#e9eef5", "surface": "#ffffff", "surface2": "#f3f6fa", "border": "#c8d2df",
    "text": "#132033", "muted": "#627086", "accent": "#245fc7", "accent_hover": "#184da8",
    "live": "#087f57", "warning": "#a96400", "danger": "#bd3043", "video": "#0c1118",
    "timeline": "#e7edf5", "tick": "#66758a", "selection": "#c5d9fb",
    "recorded": "#8bb5ed", "assist": "#8264cc", "prediction": "#a96400", "playhead": "#132033",
    "valid_soft": "#dcefe7", "foul_soft": "#f7dfe3", "review_soft": "#fff0c9", "pending_soft": "#edf2f8",
    "button_bg": "#f7f9fc", "button_hover": "#e7effb", "button_pressed": "#d8e4f5",
    "button_border": "#9faec2", "button_border_hover": "#5b7fac",
    "button_disabled_bg": "#edf1f6", "button_disabled_border": "#d2dae5", "button_disabled_text": "#8b97a8",
    "primary_pressed": "#174998", "success_hover": "#0a9668", "success_pressed": "#076344",
    "danger_hover": "#d94356", "danger_pressed": "#922334", "warning_hover": "#c77a08", "warning_pressed": "#895100",
    "neutral_bg": "#e1e7ef", "neutral_hover": "#d3dce8", "neutral_pressed": "#c2cedd",
}


BUTTON_STYLES = {
    "secondary": "Secondary.TButton",
    "primary": "Primary.TButton",
    "success": "Success.TButton",
    "danger": "Danger.TButton",
    "warning": "Warning.TButton",
    "neutral": "Neutral.TButton",
    "toolbar": "Toolbar.TButton",
    "icon": "Icon.TButton",
    "destructive": "Destructive.TButton",
    "pending": "JudgePending.TButton",
    "valid": "JudgeValid.TButton",
    "foul": "JudgeFoul.TButton",
    "review": "JudgeReview.TButton",
}


def button_style(variant: str = "secondary") -> str:
    """Return the shared ttk style name for a semantic button variant."""
    try:
        return BUTTON_STYLES[variant.strip().lower()]
    except (AttributeError, KeyError) as exc:
        choices = ", ".join(sorted(BUTTON_STYLES))
        raise ValueError(f"Unknown button variant {variant!r}; choose one of: {choices}") from exc

def _theme_palette_for(widget: tk.Misc) -> dict[str, str]:
    """Return the active palette for a widget and its themed parent chain."""
    current: tk.Misc | None = widget
    while current is not None:
        palette = getattr(current, "_ljr_palette", None)
        if isinstance(palette, dict):
            return palette
        try:
            current = current.master
        except AttributeError:
            current = None
    return DARK


def _popup_is_fullscreen(window: tk.Toplevel) -> bool:
    """Return Tk's fullscreen state without treating the string ``"0"`` as true."""
    try:
        value = window.attributes("-fullscreen")
    except tk.TclError:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return value is True or value == 1


def _win32_window_and_monitor_rects(
    window: tk.Toplevel,
    reference: tk.Misc,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None:
    """Measure the decorated popup and the full monitor containing its parent."""
    if sys.platform != "win32":
        return None

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    try:
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        popup_handle = user32.GetAncestor(int(window.winfo_id()), 2)  # GA_ROOT
        reference_handle = user32.GetAncestor(int(reference.winfo_id()), 2)
        if not popup_handle:
            popup_handle = int(window.winfo_id())
        if not reference_handle:
            reference_handle = popup_handle

        popup_rect = wintypes.RECT()
        if not user32.GetWindowRect(popup_handle, ctypes.byref(popup_rect)):
            return None
        monitor = user32.MonitorFromWindow(reference_handle, 2)  # nearest monitor
        monitor_info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
            return None
        return (
            (popup_rect.left, popup_rect.top, popup_rect.right, popup_rect.bottom),
            (
                monitor_info.rcMonitor.left,
                monitor_info.rcMonitor.top,
                monitor_info.rcMonitor.right,
                monitor_info.rcMonitor.bottom,
            ),
        )
    except (AttributeError, OSError, tk.TclError, TypeError, ValueError):
        return None


def center_popup(window: tk.Toplevel, parent: tk.Misc | None = None) -> None:
    """Center an application popup's decorated frame on its parent's screen."""
    reference = parent or getattr(window, "master", None) or window

    def apply_position() -> None:
        window._ljr_center_popup_job = None
        try:
            if not window.winfo_exists() or _popup_is_fullscreen(window):
                return
            window.update_idletasks()
            width = window.winfo_width()
            height = window.winfo_height()
            if width <= 1:
                width = max(1, window.winfo_reqwidth())
            if height <= 1:
                height = max(1, window.winfo_reqheight())
            window.geometry(f"{width}x{height}")
            window.update_idletasks()
            measured = _win32_window_and_monitor_rects(window, reference)
            if measured is not None:
                popup_rect, screen_rect = measured
                outer_width = max(1, popup_rect[2] - popup_rect[0])
                outer_height = max(1, popup_rect[3] - popup_rect[1])
                x = screen_rect[0] + (screen_rect[2] - screen_rect[0] - outer_width) // 2
                y = screen_rect[1] + (screen_rect[3] - screen_rect[1] - outer_height) // 2
                popup_handle = ctypes.windll.user32.GetAncestor(int(window.winfo_id()), 2)
                ctypes.windll.user32.SetWindowPos(popup_handle, 0, x, y, 0, 0, 0x0015)
            else:
                x = (window.winfo_screenwidth() - width) // 2
                y = (window.winfo_screenheight() - height) // 2
                window.geometry(f"{width}x{height}{x:+d}{y:+d}")
        except tk.TclError:
            pass

    def schedule_position() -> None:
        try:
            previous = getattr(window, "_ljr_center_popup_job", None)
            if previous is not None:
                window.after_cancel(previous)
            window._ljr_center_popup_job = window.after_idle(apply_position)
        except tk.TclError:
            pass

    try:
        if window.winfo_ismapped():
            schedule_position()
            return
        binding_id: str | None = None

        def refine_after_map(_event: tk.Event) -> None:
            if binding_id is not None:
                try:
                    window.unbind("<Map>", binding_id)
                except tk.TclError:
                    pass
            schedule_position()

        binding_id = window.bind("<Map>", refine_after_map, add="+")
    except tk.TclError:
        pass


def configure_popup(window: tk.Toplevel, parent: tk.Misc) -> dict[str, str]:
    """Give every application-owned popup the same surface as the main app."""
    palette = _theme_palette_for(parent)
    window.configure(bg=palette["bg"])
    try:
        window.option_add("*Dialog*background", palette["bg"])
    except tk.TclError:
        pass
    center_popup(window, parent)
    return palette


def style_popup_menu(menu: tk.Menu, parent: tk.Misc) -> None:
    palette = _theme_palette_for(parent)
    try:
        menu.configure(
            background=palette["surface"], foreground=palette["text"],
            activebackground=palette["selection"], activeforeground=palette["text"],
            disabledforeground=palette["muted"], selectcolor=palette["accent"],
            font=("Segoe UI", 11), borderwidth=1, relief="solid", activeborderwidth=0,
        )
    except tk.TclError:
        pass


def bind_resize_only(
    widget: tk.Misc,
    callback: Callable[[tk.Event], object | None],
    *,
    add: str = "+",
) -> str:
    """Bind a callback to actual size changes, ignoring window movement.

    Tk sends ``<Configure>`` for both geometry changes and changes to a
    toplevel's screen position.  Rendering/layout callbacks should normally
    respond to width/height changes only; otherwise dragging a window can
    repeatedly rebuild expensive video or settings content for no visual
    reason.
    """
    last_size: tuple[int, int] | None = None

    def on_configure(event: tk.Event) -> object | None:
        nonlocal last_size
        try:
            size = (int(event.width), int(event.height))
        except (AttributeError, TypeError, ValueError):
            try:
                size = (int(widget.winfo_width()), int(widget.winfo_height()))
            except (tk.TclError, TypeError, ValueError):
                return None
        if size == last_size:
            return None
        last_size = size
        return callback(event)

    return widget.bind("<Configure>", on_configure, add=add)


def _dialog_kind_from_text(title: str, message: str) -> str:
    """Choose a useful semantic icon for legacy informational call sites."""
    text = f"{title} {message}".lower()
    if any(token in text for token in ("error", "failed", "could not", "cannot", "unable", "invalid", "exception")):
        return "error"
    if any(token in text for token in ("warning", "conflict", "unsaved", "nothing was changed")):
        return "warning"
    return "info"


def _dialog_icon(parent: tk.Misc, palette: dict[str, str], kind: str) -> tk.Canvas:
    """Create a compact Windows-like semantic symbol without external assets."""
    symbols = {
        "info": ("i", palette["accent"], palette["text"]),
        "warning": ("!", palette["warning"], "#111722"),
        "error": ("×", palette["danger"], palette["text"]),
        "question": ("?", palette["accent"], palette["text"]),
    }
    symbol, fill, foreground = symbols.get(kind, symbols["info"])
    icon = tk.Canvas(parent, width=30, height=30, highlightthickness=0, bd=0, bg=palette["surface"])
    icon.create_oval(2, 2, 28, 28, fill=fill, outline="")
    icon.create_text(15, 15, text=symbol, fill=foreground, font=("Segoe UI Semibold", 13))
    return icon


def themed_message(
    parent: tk.Misc,
    title: str,
    message: str,
    *,
    buttons: tuple[tuple[str, str, str], ...] = (("OK", "ok", "Primary.TButton"),),
    width: int = 440,
    kind: str = "info",
) -> str:
    """Show a blocking, ttk-themed message/confirmation dialog."""
    palette = _theme_palette_for(parent)
    try:
        previous_grab = parent.grab_current()
    except tk.TclError:
        previous_grab = None
    dialog = tk.Toplevel(parent)
    configure_popup(dialog, parent)
    dialog.title(title)
    dialog.resizable(False, False)
    dialog.transient(parent)
    result = tk.StringVar(dialog, value="")
    body = ttk.Frame(dialog, style="Dialog.TFrame", padding=(17, 14, 17, 10))
    body.pack(fill="both", expand=True)
    header = ttk.Frame(body, style="Dialog.TFrame")
    header.pack(fill="x")
    _dialog_icon(header, palette, kind).pack(side="left", padx=(0, 10))
    ttk.Label(header, text=title, style="DialogTitle.TLabel").pack(side="left", anchor="center")
    ttk.Label(body, text=message, style="DialogBody.TLabel", wraplength=width - 34, justify="left").pack(anchor="w", pady=(6, 13))
    footer = ttk.Frame(body, style="Dialog.TFrame")
    footer.pack(fill="x")
    for label, value, style in buttons:
        ttk.Button(footer, text=label, style=style, command=lambda value=value: result.set(value)).pack(side="right", padx=(7, 0))
    dialog.protocol("WM_DELETE_WINDOW", lambda: result.set("cancel"))
    dialog.update_idletasks()
    height = max(130, body.winfo_reqheight())
    screen_w, screen_h = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
    dialog.geometry(f"{width}x{height}+{max(0, (screen_w - width) // 2)}+{max(0, (screen_h - height) // 2)}")
    dialog.grab_set()
    dialog.wait_variable(result)
    value = result.get() or "cancel"
    try:
        dialog.grab_release()
        dialog.destroy()
    except tk.TclError:
        pass
    if previous_grab is not None:
        try:
            if previous_grab.winfo_exists():
                previous_grab.grab_set()
                previous_grab.lift()
        except tk.TclError:
            pass
    return value


def show_themed_info(parent: tk.Misc, title: str, message: str) -> None:
    themed_message(parent, title, message, kind=_dialog_kind_from_text(title, message))


def show_themed_warning(parent: tk.Misc, title: str, message: str) -> None:
    themed_message(parent, title, message, kind="warning")


def show_themed_error(parent: tk.Misc, title: str, message: str) -> None:
    themed_message(parent, title, message, kind="error")


def ask_themed_yes_no(parent: tk.Misc, title: str, message: str, *, yes: str = "Yes", no: str = "No") -> bool:
    return themed_message(
        parent, title, message,
        buttons=((no, "no", "Secondary.TButton"), (yes, "yes", "Primary.TButton")),
        kind="question",
    ) == "yes"


def ask_themed_yes_no_cancel(
    parent: tk.Misc, title: str, message: str, *, yes: str = "Yes", no: str = "No", cancel: str = "Cancel",
) -> bool | None:
    value = themed_message(
        parent, title, message,
        buttons=((cancel, "cancel", "Secondary.TButton"), (no, "no", "Secondary.TButton"), (yes, "yes", "Primary.TButton")),
        kind="question",
    )
    return True if value == "yes" else False if value == "no" else None


def system_prefers_dark() -> bool:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return int(value) == 0
        except Exception:
            pass
    return os.environ.get("COLORFGBG", "").split(";")[-1:] == ["0"]


class ThemeManager:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.tk_scaling = apply_compact_ui_scaling(root)
        self.palette = DARK
        self.name = "dark"
        self._image_assets: dict[str, tk.PhotoImage] = {}
        self._popup_binding_installed = False

    def _checkbox_image(self, key: str, border: str, fill: str, checked: bool) -> tk.PhotoImage:
        size, centre, outer, inner = 16, 7.5, 7.0, 5.25
        image = tk.PhotoImage(master=self.root, width=size, height=size)
        for y in range(size):
            for x in range(size):
                distance = ((x - centre) ** 2 + (y - centre) ** 2) ** .5
                if distance <= outer:
                    image.put(fill if distance <= inner else border, to=(x, y))
        if checked:
            for x, y in ((4, 7), (5, 8), (6, 9), (7, 10), (8, 9), (9, 8), (10, 7), (11, 6), (12, 5)):
                image.put("#ffffff", to=(x, y, min(size, x + 2), min(size, y + 2)))
        self._image_assets[key] = image
        return image

    def _install_checkbox_style(self, style: ttk.Style, p: dict[str, str]) -> None:
        prefix = f"Modern{self.name.title()}"
        element = f"{prefix}.Check.indicator"
        if element not in style.element_names():
            unchecked = self._checkbox_image(f"{prefix}.unchecked", p["muted"], p["surface2"], False)
            checked = self._checkbox_image(f"{prefix}.checked", p["accent"], p["accent"], True)
            disabled = self._checkbox_image(f"{prefix}.disabled", p["border"], p["surface"], False)
            disabled_checked = self._checkbox_image(f"{prefix}.disabled_checked", p["muted"], p["muted"], True)
            style.element_create(
                element, "image", unchecked,
                ("disabled", "selected", disabled_checked), ("selected", checked), ("disabled", disabled),
                sticky="",
            )
        style.layout("TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                (element, {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])

    def _rounded_image(self, key: str, fill: str, border: str, radius: int = BUTTON_CORNER_RADIUS) -> tk.PhotoImage:
        # This is a scalable nine-slice background, not the final control size.
        # Keep its centre compact so rounding does not inflate every button.
        width, height = 40, 28
        image = tk.PhotoImage(master=self.root, width=width, height=height)
        for y in range(height):
            colors: list[str] = []
            for x in range(width):
                dx = max(radius - x, x - (width - radius - 1), 0)
                dy = max(radius - y, y - (height - radius - 1), 0)
                inside = dx * dx + dy * dy <= radius * radius
                inner = dx * dx + dy * dy <= max(1, radius - 1) ** 2
                colors.append(fill if inside and inner else border if inside else "")
            start = 0
            while start < width:
                color = colors[start]
                end = start + 1
                while end < width and colors[end] == color:
                    end += 1
                if color:
                    image.put(color, to=(start, y, end, y + 1))
                start = end
        self._image_assets[key] = image
        return image

    def _install_rounded_button_style(
        self,
        style: ttk.Style,
        style_name: str,
        role: str,
        *,
        normal: str,
        hover: str,
        pressed: str,
        border: str,
        hover_border: str,
        foreground: str,
        disabled_foreground: str,
        padding: tuple[int, int],
        font: tuple,
        selected: str | None = None,
        selected_border: str | None = None,
        anchor: str = "center",
    ) -> None:
        prefix = f"Modern{self.name.title()}.{role}"
        element = f"{prefix}.Button.background"
        if element not in style.element_names():
            normal_image = self._rounded_image(f"{prefix}.normal", normal, border)
            hover_image = self._rounded_image(f"{prefix}.hover", hover, hover_border)
            pressed_image = self._rounded_image(f"{prefix}.pressed", pressed, hover_border)
            focus_image = self._rounded_image(f"{prefix}.focus", normal, self.palette["accent"])
            selected_image = self._rounded_image(
                f"{prefix}.selected", selected or pressed, selected_border or self.palette["text"]
            )
            disabled_image = self._rounded_image(
                f"{prefix}.disabled", self.palette["button_disabled_bg"], self.palette["button_disabled_border"]
            )
            style.element_create(
                element, "image", normal_image,
                ("disabled", disabled_image), ("pressed", pressed_image), ("selected", selected_image),
                ("focus", focus_image), ("active", hover_image),
                border=(BUTTON_CORNER_RADIUS,) * 4, sticky="nswe",
            )
        style.layout(style_name, [(element, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]}),
        ]})])
        style.configure(
            style_name,
            padding=padding,
            font=font,
            anchor=anchor,
            justify="center" if anchor == "center" else "left",
            # The semantic colour lives in the rounded image. Keeping the
            # widget backing neutral prevents transparent corners from being
            # refilled into a bright rectangular block by ttk.
            background=self.palette["bg"],
            foreground=foreground,
            borderwidth=0,
            relief="flat",
        )
        style.map(
            style_name,
            background=[
                ("disabled", self.palette["bg"]),
                ("pressed", self.palette["bg"]),
                ("selected", self.palette["bg"]),
                ("active", self.palette["bg"]),
            ],
            foreground=[
                ("disabled", disabled_foreground),
                ("pressed", foreground),
                ("selected", foreground),
                ("focus", foreground),
                ("active", foreground),
            ],
        )

    def _install_rounded_controls(self, style: ttk.Style, p: dict[str, str]) -> None:
        """Install the shared semantic button family, including legacy aliases."""
        regular_font = ("Segoe UI", 10)
        strong_font = ("Segoe UI Semibold", 10)
        important_font = ("Segoe UI Semibold", 10)
        standard_padding = (12, 4)
        compact_padding = (9, 3)
        judge_padding = (12, 5)
        disabled = p["button_disabled_text"]

        roles = {
            "secondary": dict(normal=p["button_bg"], hover=p["button_hover"], pressed=p["button_pressed"], border=p["button_border"], hover_border=p["button_border_hover"], foreground=p["text"], padding=standard_padding, font=regular_font, selected=p["selection"]),
            "primary": dict(normal=p["accent"], hover=p["accent_hover"], pressed=p["primary_pressed"], border=p["accent"], hover_border=p["accent_hover"], foreground="#ffffff", padding=standard_padding, font=strong_font, selected=p["primary_pressed"]),
            "success": dict(normal=p["live"], hover=p["success_hover"], pressed=p["success_pressed"], border=p["live"], hover_border=p["success_hover"], foreground="#ffffff", padding=standard_padding, font=strong_font, selected=p["success_pressed"]),
            "danger": dict(normal=p["foul_soft"], hover=p["danger"], pressed=p["danger_pressed"], border=p["danger"], hover_border=p["danger_hover"], foreground=p["text"], padding=standard_padding, font=strong_font, selected=p["danger_pressed"]),
            "warning": dict(normal=p["warning"], hover=p["warning_hover"], pressed=p["warning_pressed"], border=p["warning"], hover_border=p["warning_hover"], foreground="#111820", padding=standard_padding, font=strong_font, selected=p["warning_pressed"]),
            "neutral": dict(normal=p["neutral_bg"], hover=p["neutral_hover"], pressed=p["neutral_pressed"], border=p["button_border"], hover_border=p["button_border_hover"], foreground=p["text"], padding=standard_padding, font=regular_font, selected=p["selection"]),
            "toolbar": dict(normal=p["button_bg"], hover=p["button_hover"], pressed=p["button_pressed"], border=p["button_border"], hover_border=p["button_border_hover"], foreground=p["text"], padding=compact_padding, font=regular_font, selected=p["selection"]),
            "icon": dict(normal=p["button_bg"], hover=p["button_hover"], pressed=p["button_pressed"], border=p["button_border"], hover_border=p["button_border_hover"], foreground=p["text"], padding=(7, 4), font=regular_font, selected=p["selection"]),
            "destructive": dict(normal=p["danger"], hover=p["danger_hover"], pressed=p["danger_pressed"], border=p["danger"], hover_border=p["danger_hover"], foreground="#ffffff", padding=standard_padding, font=strong_font, selected=p["danger_pressed"]),
            "judge_pending": dict(normal=p["neutral_bg"], hover=p["neutral_hover"], pressed=p["neutral_pressed"], border=p["button_border"], hover_border=p["button_border_hover"], foreground="#ffffff", padding=judge_padding, font=important_font, selected=p["neutral_pressed"], selected_border="#ffffff"),
            "judge_valid": dict(normal=p["live"], hover=p["success_hover"], pressed=p["success_pressed"], border=p["live"], hover_border=p["success_hover"], foreground="#ffffff", padding=judge_padding, font=important_font, selected=p["success_pressed"], selected_border="#ffffff"),
            "judge_foul": dict(normal=p["danger"], hover=p["danger_hover"], pressed=p["danger_pressed"], border=p["danger"], hover_border=p["danger_hover"], foreground="#ffffff", padding=judge_padding, font=important_font, selected=p["danger_pressed"], selected_border="#ffffff"),
            "judge_review": dict(normal=p["warning"], hover=p["warning_hover"], pressed=p["warning_pressed"], border=p["warning"], hover_border=p["warning_hover"], foreground="#111820", padding=judge_padding, font=important_font, selected=p["warning_pressed"], selected_border="#111820"),
        }
        assignments = {
            "TButton": "secondary",
            "Secondary.TButton": "secondary",
            "Primary.TButton": "primary",
            "Success.TButton": "success",
            "Danger.TButton": "danger",
            "Warning.TButton": "warning",
            "Neutral.TButton": "neutral",
            "Toolbar.TButton": "toolbar",
            "Icon.TButton": "icon",
            "Destructive.TButton": "destructive",
            "JudgePending.TButton": "judge_pending",
            "JudgeValid.TButton": "judge_valid",
            "JudgeFoul.TButton": "judge_foul",
            "JudgeReview.TButton": "judge_review",
            # Compatibility aliases keep plug-ins and late-created dialogs on
            # the same system while the application uses semantic names.
            "Control.TButton": "secondary",
            "Accent.TButton": "primary",
            "Live.TButton": "success",
            "PrimaryJudge.TButton": "primary",
            "LiveJudge.TButton": "success",
            "MutedAction.TButton": "neutral",
            "SystemPause.TButton": "warning",
            "SystemResume.TButton": "success",
            "Valid.TButton": "success",
            "Foul.TButton": "danger",
            "Review.TButton": "warning",
            "Projection.TButton": "toolbar",
            "Projection.Accent.TButton": "primary",
        }
        for style_name, role in assignments.items():
            values = roles[role]
            self._install_rounded_button_style(
                style,
                style_name,
                role,
                disabled_foreground=disabled,
                **values,
            )

        # Sidebar navigation is button-like but uses persistent selection and
        # left-aligned labels rather than the centered action-button layout.
        for style_name in ("Sidebar.TButton", "SettingsNav.TButton"):
            self._install_rounded_button_style(
                style,
                style_name,
                "navigation",
                disabled_foreground=disabled,
                anchor="w",
                **roles["toolbar"],
            )
        self._install_rounded_menubutton(style, "TMenubutton", "menu")
        self._install_rounded_menubutton(style, "Header.TMenubutton", "header_menu")

    def _install_rounded_menubutton(self, style: ttk.Style, style_name: str, role: str) -> None:
        """Give File/View/Camera/Help selectors the same rounded surface."""
        prefix = f"Modern{self.name.title()}.{role}"
        element = f"{prefix}.Menubutton.background"
        p = self.palette
        if element not in style.element_names():
            normal = self._rounded_image(f"{prefix}.normal", p["button_bg"], p["button_border"])
            hover = self._rounded_image(f"{prefix}.hover", p["button_hover"], p["button_border_hover"])
            pressed = self._rounded_image(f"{prefix}.pressed", p["button_pressed"], p["button_border_hover"])
            focus = self._rounded_image(f"{prefix}.focus", p["button_bg"], p["accent"])
            disabled = self._rounded_image(f"{prefix}.disabled", p["button_disabled_bg"], p["button_disabled_border"])
            style.element_create(
                element, "image", normal,
                ("disabled", disabled), ("pressed", pressed), ("focus", focus), ("active", hover),
                border=(BUTTON_CORNER_RADIUS,) * 4, sticky="nswe",
            )
        style.layout(style_name, [(element, {"sticky": "nswe", "children": [
            ("Menubutton.focus", {"sticky": "nswe", "children": [
                ("Menubutton.indicator", {"side": "right", "sticky": ""}),
                ("Menubutton.padding", {"sticky": "we", "children": [
                    ("Menubutton.label", {"side": "left", "sticky": ""}),
                ]}),
            ]}),
        ]})])
        style.configure(
            style_name,
            background=p["bg"], foreground=p["text"], padding=(10, 4),
            borderwidth=0, relief="flat", arrowcolor=p["muted"], font=("Segoe UI", 10),
        )
        style.map(
            style_name,
            background=[("disabled", p["bg"]), ("pressed", p["bg"]), ("focus", p["bg"]), ("active", p["bg"])],
            foreground=[("disabled", p["button_disabled_text"]), ("active", p["text"]), ("pressed", p["text"])],
            arrowcolor=[("disabled", p["button_disabled_text"]), ("active", p["text"]), ("pressed", p["text"])],
        )

    @staticmethod
    def _round_native_window(window_id: int) -> None:
        if sys.platform != "win32" or not window_id:
            return
        try:
            preference = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(window_id), 33, ctypes.byref(preference), ctypes.sizeof(preference))
        except (AttributeError, OSError):
            pass

    def _round_widget_window(self, widget: tk.Misc) -> None:
        try:
            self.root.after_idle(lambda: self._round_native_window(widget.winfo_id()))
        except tk.TclError:
            pass

    def _round_combobox_popup(self, event: tk.Event) -> None:
        widget = event.widget
        def apply_rounding() -> None:
            try:
                popdown = widget.tk.call("ttk::combobox::PopdownWindow", str(widget))
                window_id = int(str(widget.tk.call("winfo", "id", popdown)), 0)
                self._round_native_window(window_id)
            except (tk.TclError, TypeError, ValueError):
                pass
        self.root.after(20, apply_rounding)

    def style_menu(self, menu: tk.Menu) -> None:
        p = self.palette
        try:
            menu.configure(
                background=p["surface"], foreground=p["text"],
                activebackground=p["selection"], activeforeground=p["text"],
                disabledforeground=p["muted"], selectcolor=p["accent"],
                font=("Segoe UI", 11), borderwidth=1, relief="solid", activeborderwidth=0,
            )
        except tk.TclError:
            pass
        menu.bind("<Map>", lambda _event, m=menu: self._round_widget_window(m), add="+")

    def apply(self, requested: str) -> dict[str, str]:
        name = "dark" if requested == "dark" or (requested == "system" and system_prefers_dark()) else "light"
        self.name = name
        self.palette = DARK if name == "dark" else LIGHT
        p = self.palette
        self.root._ljr_palette = p
        self.root.configure(background=p["bg"])
        style = ttk.Style(self.root)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure(".", background=p["bg"], foreground=p["text"], fieldbackground=p["surface2"], bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"], font=("Segoe UI", 10))
        style.configure("App.TFrame", background=p["bg"])
        style.configure("Panel.TFrame", background=p["surface"])
        style.configure("Toolbar.TFrame", background=p["surface2"])
        style.configure("JudgeHeader.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("ControlDock.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("Brand.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 15))
        style.configure("BrandSub.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        self._install_rounded_controls(style, p)
        style.configure("TMenubutton", background=p["button_bg"], foreground=p["text"], padding=(12, 5), borderwidth=1, relief="flat", arrowcolor=p["muted"], font=("Segoe UI", 10))
        style.map("TMenubutton", background=[("disabled", p["button_disabled_bg"]), ("pressed", p["button_pressed"]), ("focus", p["button_hover"]), ("active", p["button_hover"])], foreground=[("disabled", p["button_disabled_text"]), ("active", p["text"]), ("pressed", p["text"])], bordercolor=[("focus", p["accent"]), ("active", p["button_border_hover"])], arrowcolor=[("disabled", p["button_disabled_text"]), ("active", p["text"])])
        style.configure("Header.TMenubutton", background=p["button_bg"], foreground=p["text"], padding=(10, 4), borderwidth=1, relief="flat", arrowcolor=p["muted"], font=("Segoe UI", 10))
        style.map("Header.TMenubutton", background=[("disabled", p["button_disabled_bg"]), ("pressed", p["button_pressed"]), ("focus", p["button_hover"]), ("active", p["button_hover"])], foreground=[("disabled", p["button_disabled_text"]), ("active", p["text"]), ("pressed", p["text"])], bordercolor=[("focus", p["accent"]), ("active", p["button_border_hover"])], arrowcolor=[("disabled", p["button_disabled_text"]), ("active", p["text"])])
        style.configure("ContextTitle.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 9))
        style.configure("ContextValue.TLabel", background=p["surface2"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI Semibold", 14))
        style.configure("PanelTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("Text.TLabel", background=p["surface"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["surface"], foreground=p["muted"])
        style.configure("Warning.TLabel", background=p["surface"], foreground=p["warning"])
        style.configure("HeaderMuted.TLabel", background=p["bg"], foreground=p["muted"])
        style.configure("Status.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("StatusWarning.TLabel", background=p["surface2"], foreground=p["warning"], font=("Segoe UI Semibold", 9))
        style.configure("TimelineHint.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 9), padding=(4, 1))
        style.configure(
            "Modal.Horizontal.TProgressbar",
            troughcolor=p["surface2"],
            background=p["accent"],
            bordercolor=p["border"],
            lightcolor=p["accent"],
            darkcolor=p["accent"],
            borderwidth=1,
            relief="flat",
            thickness=10,
        )
        style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"], rowheight=19, borderwidth=0)
        style.configure("Treeview.Heading", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 9), relief="flat")
        style.map("Treeview", background=[("selected", p["selection"])], foreground=[("selected", p["text"])])
        style.configure("TPanedwindow", background=p["border"], sashwidth=5)
        style.configure("TNotebook", background=p["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(7, 3), background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", p["surface"])], foreground=[("selected", p["text"])])
        style.configure("TCheckbutton", background=p["surface"], foreground=p["text"], padding=(1, 2), indicatorsize=16, indicatormargin=(0, 0, 5, 0))
        style.map("TCheckbutton", background=[("active", p["surface"])], foreground=[("disabled", p["muted"]), ("active", p["text"])])
        self._install_checkbox_style(style, p)
        style.configure("TRadiobutton", background=p["surface"], foreground=p["text"])
        style.configure("TEntry", fieldbackground=p["surface2"], foreground=p["text"], insertcolor=p["text"])
        style.map("TEntry", fieldbackground=[("disabled", p["surface"]), ("readonly", p["surface2"])], foreground=[("disabled", p["muted"])])
        style.configure("TSpinbox", fieldbackground=p["surface2"], foreground=p["text"], arrowcolor=p["text"], insertcolor=p["text"])
        style.map("TSpinbox", fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])], foreground=[("readonly", p["text"]), ("disabled", p["muted"])])
        style.configure("TCombobox", fieldbackground=p["button_bg"], foreground=p["text"], arrowcolor=p["muted"], selectbackground=p["selection"], selectforeground=p["text"], padding=(10, 5), borderwidth=1, relief="flat", arrowsize=12)
        style.map("TCombobox", fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])], foreground=[("readonly", p["text"]), ("disabled", p["muted"])], bordercolor=[("focus", p["accent"]), ("active", p["accent"]), ("readonly", p["border"])], arrowcolor=[("active", p["text"]), ("readonly", p["muted"])], selectbackground=[("readonly", p["surface2"])], selectforeground=[("readonly", p["text"])])
        for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.configure(scrollbar_style, background=p["surface2"], troughcolor=p["bg"], arrowcolor=p["muted"], bordercolor=p["border"], lightcolor=p["surface2"], darkcolor=p["border"], relief="flat")
            style.map(scrollbar_style, background=[("disabled", p["surface"]), ("pressed", p["accent"]), ("active", p["selection"])], arrowcolor=[("disabled", p["muted"]), ("active", p["text"]), ("pressed", p["text"])])
        style.configure("ImpactLow.TLabel", background=p["surface"], foreground=p["live"], font=("Segoe UI Semibold", 8))
        style.configure("ImpactMedium.TLabel", background=p["surface"], foreground=p["warning"], font=("Segoe UI Semibold", 8))
        style.configure("ImpactHigh.TLabel", background=p["surface"], foreground=p["danger"], font=("Segoe UI Semibold", 8))
        style.configure("ImpactVeryHigh.TLabel", background=p["surface"], foreground=p["danger"], font=("Segoe UI Semibold", 8, "underline"))
        style.configure("ImpactNone.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("SettingsHeader.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("SettingsSidebar.TFrame", background=p["surface2"], borderwidth=1, relief="solid")
        style.configure("SettingsHero.TFrame", background=p["surface2"], borderwidth=1, relief="solid")
        style.configure("SettingsHeroTitle.TLabel", background=p["surface2"], foreground=p["text"], font=("Segoe UI Semibold", 18))
        style.configure("SettingsHeroDesc.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("SettingsGroup.TFrame", background=p["surface2"])
        style.configure("SettingsGroup.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 8))
        style.configure("SettingsDirty.TLabel", background=p["surface"], foreground=p["warning"], font=("Segoe UI Semibold", 8))
        style.configure("SettingsRow.TFrame", background=p["surface"], borderwidth=0, relief="flat")
        style.configure("SettingsSearchHit.TFrame", background=p["selection"], borderwidth=1, relief="solid")
        style.configure("SettingsRowTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("SettingsRowDesc.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("SettingsSection.TLabelframe", background=p["surface"], bordercolor=p["border"], relief="solid", borderwidth=1)
        style.configure("SettingsSection.TLabelframe.Label", background=p["surface"], foreground=p["muted"], font=("Segoe UI Semibold", 9))
        style.configure("WizardRail.TFrame", background=p["surface2"], borderwidth=1, relief="solid")
        style.configure("WizardRail.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 9), padding=(9, 6))
        style.configure("WizardRailActive.TLabel", background=p["selection"], foreground=p["text"], font=("Segoe UI Semibold", 9), padding=(9, 6))
        style.configure("WizardCard.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("WizardCardTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 13))
        style.configure("WizardHeroTitle.TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI Semibold", 22))
        style.configure("WizardHeroDesc.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 10))
        style.configure("WizardReady.TLabel", background=p["surface"], foreground=p["live"], font=("Segoe UI Semibold", 9))
        style.configure("WizardWarm.TLabel", background=p["surface"], foreground=p["warning"], font=("Segoe UI Semibold", 9))
        style.configure("WizardDanger.TLabel", background=p["surface"], foreground=p["danger"], font=("Segoe UI Semibold", 9))
        style.configure("Dialog.TFrame", background=p["surface"])
        style.configure("DialogTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 13))
        style.configure("DialogBody.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 10))
        # ttk combobox pop-downs use a classic rectangular Tk Listbox on Windows.
        self.root.option_add("*TCombobox*Listbox.background", p["surface2"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["selection"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["text"])
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))
        self.root.option_add("*TCombobox*Listbox.relief", "flat")
        self.root.option_add("*TCombobox*Listbox.borderWidth", 1)
        self.root.option_add("*TCombobox*Listbox.activestyle", "none")
        self.root.option_add("*Listbox.background", p["surface2"])
        self.root.option_add("*Listbox.foreground", p["text"])
        self.root.option_add("*Listbox.selectBackground", p["selection"])
        self.root.option_add("*Listbox.selectForeground", p["text"])
        self.root.option_add("*Menu.background", p["surface"])
        self.root.option_add("*Menu.foreground", p["text"])
        self.root.option_add("*Menu.activeBackground", p["selection"])
        self.root.option_add("*Menu.activeForeground", p["text"])
        self.root.option_add("*Menu.disabledForeground", p["muted"])
        self.root.option_add("*Menu.selectColor", p["accent"])
        self.root.option_add("*Menu.font", ("Segoe UI", 10))
        return p
