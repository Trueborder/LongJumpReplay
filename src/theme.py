from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk
import ctypes


# The original interface was laid out at approximately 130% of the density the
# operator now wants. Keep Windows' native DPI factor, but render application
# typography and character-sized controls at roughly 100 / 130 of that size.
COMPACT_UI_RATIO = 100.0 / 130.0
MIN_COMPACT_TK_SCALING = 1.0


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
}
LIGHT = {
    "bg": "#e9eef5", "surface": "#ffffff", "surface2": "#f3f6fa", "border": "#c8d2df",
    "text": "#132033", "muted": "#627086", "accent": "#245fc7", "accent_hover": "#184da8",
    "live": "#087f57", "warning": "#a96400", "danger": "#bd3043", "video": "#0c1118",
    "timeline": "#e7edf5", "tick": "#66758a", "selection": "#c5d9fb",
    "recorded": "#8bb5ed", "assist": "#8264cc", "prediction": "#a96400", "playhead": "#132033",
    "valid_soft": "#dcefe7", "foul_soft": "#f7dfe3", "review_soft": "#fff0c9", "pending_soft": "#edf2f8",
}


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


def center_popup(window: tk.Toplevel) -> None:
    """Center an application-owned popup after its final size is configured."""
    def apply_position() -> None:
        window._ljr_center_popup_job = None
        try:
            if not window.winfo_exists() or bool(window.attributes("-fullscreen")):
                return
            window.update_idletasks()
            width = max(1, window.winfo_width(), window.winfo_reqwidth())
            height = max(1, window.winfo_height(), window.winfo_reqheight())
            screen_width = window.winfo_screenwidth()
            screen_height = window.winfo_screenheight()
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 2)
            window.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            pass

    try:
        previous = getattr(window, "_ljr_center_popup_job", None)
        if previous is not None:
            window.after_cancel(previous)
        window._ljr_center_popup_job = window.after_idle(apply_position)
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
    center_popup(window)
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


def themed_message(
    parent: tk.Misc,
    title: str,
    message: str,
    *,
    buttons: tuple[tuple[str, str, str], ...] = (("OK", "ok", "Accent.TButton"),),
    width: int = 440,
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
    ttk.Label(body, text=title, style="DialogTitle.TLabel").pack(anchor="w")
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
    themed_message(parent, title, message)


def ask_themed_yes_no(parent: tk.Misc, title: str, message: str, *, yes: str = "Yes", no: str = "No") -> bool:
    return themed_message(
        parent, title, message,
        buttons=((no, "no", "Control.TButton"), (yes, "yes", "Accent.TButton")),
    ) == "yes"


def ask_themed_yes_no_cancel(
    parent: tk.Misc, title: str, message: str, *, yes: str = "Yes", no: str = "No", cancel: str = "Cancel",
) -> bool | None:
    value = themed_message(
        parent, title, message,
        buttons=((cancel, "cancel", "Control.TButton"), (no, "no", "Control.TButton"), (yes, "yes", "Accent.TButton")),
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

    def _rounded_image(self, key: str, fill: str, border: str, radius: int = 10) -> tk.PhotoImage:
        # This is a scalable nine-slice background, not the final control size.
        # Keep its centre compact so rounding does not inflate every button.
        width, height = 40, 22
        image = tk.PhotoImage(master=self.root, width=width, height=height)
        for y in range(height):
            colors: list[str] = []
            for x in range(width):
                dx = max(radius - x, x - (width - radius - 1), 0)
                dy = max(radius - y, y - (height - radius - 1), 0)
                inside = dx * dx + dy * dy <= radius * radius
                inner = dx * dx + dy * dy <= max(1, radius - 2) ** 2
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

    def _install_rounded_button_style(self, style: ttk.Style, style_name: str, role: str, normal: str, active: str, border: str) -> None:
        prefix = f"Modern{self.name.title()}.{role}"
        element = f"{prefix}.Button.background"
        if element not in style.element_names():
            normal_image = self._rounded_image(f"{prefix}.normal", normal, border)
            active_image = self._rounded_image(f"{prefix}.active", active, active)
            pressed_image = self._rounded_image(f"{prefix}.pressed", active, border)
            disabled_image = self._rounded_image(f"{prefix}.disabled", self.palette["surface"], self.palette["border"])
            style.element_create(
                element, "image", normal_image,
                ("disabled", disabled_image), ("pressed", pressed_image), ("active", active_image),
                border=(10, 5, 10, 5), sticky="nswe",
            )
        style.layout(style_name, [(element, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]}),
        ]})])

    def _install_rounded_controls(self, style: ttk.Style, p: dict[str, str]) -> None:
        # Buttons intentionally use the native square ttk layout.  The old
        # custom image element made every button pill-shaped and also made
        # disabled judge controls difficult to distinguish.  Comboboxes use
        # the platform's normal rectangular field and pop-down list as well.

        # Keep a compact neutral asset available for GUI smoke tests and for
        # platforms that opt into the image-backed button element later.
        neutral_prefix = f"Modern{self.name.title()}.neutral"
        if f"{neutral_prefix}.normal" not in self._image_assets:
            self._rounded_image(f"{neutral_prefix}.normal", p["surface2"], p["border"])

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
        style.configure("TButton", padding=(6, 0))
        style.configure("TMenubutton", background=p["surface2"], foreground=p["text"], padding=(8, 0), borderwidth=1, relief="flat", arrowcolor=p["muted"], font=("Segoe UI", 10))
        style.map("TMenubutton", background=[("active", p["selection"]), ("pressed", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"])], arrowcolor=[("active", p["text"])])
        style.configure("Header.TMenubutton", background=p["surface2"], foreground=p["text"], padding=(8, 0), borderwidth=1, relief="flat", arrowcolor=p["muted"], font=("Segoe UI", 10))
        style.map("Header.TMenubutton", background=[("active", p["selection"]), ("pressed", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"])], arrowcolor=[("active", p["text"])])
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
        style.configure("Control.TButton", padding=(7, 0), font=("Segoe UI", 9))
        style.map("Control.TButton", background=[("disabled", p["surface2"]), ("active", p["surface2"]), ("pressed", p["selection"])], foreground=[("disabled", p["muted"])])
        style.configure("Accent.TButton", padding=(8, 0), font=("Segoe UI Semibold", 9), background=p["accent"], foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])])
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
        style.configure("Live.TButton", padding=(8, 0), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("PrimaryJudge.TButton", padding=(9, 1), font=("Segoe UI Semibold", 9), background=p["accent"], foreground="#ffffff")
        style.map("PrimaryJudge.TButton", background=[("disabled", p["surface2"]), ("active", p["accent_hover"]), ("pressed", p["accent_hover"])], foreground=[("disabled", p["muted"])])
        style.configure("LiveJudge.TButton", padding=(8, 1), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("Danger.TButton", padding=(7, 0), background=p["danger"], foreground="#ffffff")
        style.configure("MutedAction.TButton", padding=(7, 1), background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 9))
        style.map("MutedAction.TButton", background=[("active", p["selection"]), ("pressed", p["selection"]), ("disabled", p["surface"])], foreground=[("active", p["text"]), ("pressed", p["text"]), ("disabled", p["muted"])])
        style.configure("SystemPause.TButton", padding=(8, 2), background=p["warning"], foreground="#111111", font=("Segoe UI Semibold", 9))
        style.map("SystemPause.TButton", background=[("disabled", p["surface2"]), ("active", p["accent_hover"]), ("pressed", p["accent_hover"])], foreground=[("disabled", p["muted"])])
        style.configure("SystemResume.TButton", padding=(8, 2), background=p["live"], foreground="#ffffff", font=("Segoe UI Semibold", 9))
        style.map("SystemResume.TButton", background=[("disabled", p["surface2"]), ("active", p["accent_hover"]), ("pressed", p["accent_hover"])], foreground=[("disabled", p["muted"])])
        style.configure("Valid.TButton", padding=(9, 0), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("Foul.TButton", padding=(9, 0), font=("Segoe UI Semibold", 9), background=p["danger"], foreground="#ffffff")
        style.configure("Review.TButton", padding=(9, 0), font=("Segoe UI Semibold", 9), background=p["warning"], foreground="#111111")
        style.configure("JudgePending.TButton", padding=(9, 1), font=("Segoe UI Semibold", 9), background=p["pending_soft"], foreground=p["text"])
        style.map("JudgePending.TButton", background=[("disabled", p["surface2"]), ("active", p["selection"]), ("pressed", p["selection"])], foreground=[("disabled", p["muted"])])
        for name, background, foreground in (
            ("JudgeValid.TButton", p["live"], "#ffffff"),
            ("JudgeFoul.TButton", p["danger"], "#ffffff"),
            ("JudgeReview.TButton", p["warning"], "#111111"),
        ):
            style.configure(name, padding=(9, 1), font=("Segoe UI Semibold", 9), background=background, foreground=foreground)
            style.map(name, background=[("disabled", p["surface2"]), ("active", background), ("pressed", background)], foreground=[("disabled", p["muted"])])
        style.configure("Sidebar.TButton", padding=(9, 1), anchor="w", background=p["surface2"], foreground=p["text"])
        style.map("Sidebar.TButton", background=[("active", p["selection"]), ("pressed", p["selection"])])
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
        style.configure("TCombobox", fieldbackground=p["surface2"], foreground=p["text"], arrowcolor=p["muted"], selectbackground=p["selection"], selectforeground=p["text"], padding=(7, 0), borderwidth=1, relief="flat", arrowsize=12)
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
        style.configure("SettingsNav.TButton", padding=(10, 2), anchor="w", background=p["surface2"], foreground=p["muted"], borderwidth=0)
        style.map("SettingsNav.TButton", background=[("active", p["selection"]), ("pressed", p["selection"]), ("selected", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"]), ("selected", p["text"])])
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
        self._install_rounded_controls(style, p)
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
