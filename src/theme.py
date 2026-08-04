from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk
import ctypes


DARK = {
    "bg": "#090d14", "surface": "#111722", "surface2": "#182131", "border": "#2a374a",
    "text": "#f4f7fb", "muted": "#96a4b8", "accent": "#4f8cff", "accent_hover": "#78a8ff",
    "live": "#35d39a", "warning": "#f5bd4f", "danger": "#ff6675", "video": "#03060a",
    "timeline": "#0d1420", "tick": "#71839c", "selection": "#254c80",
    "valid_soft": "#12392d", "foul_soft": "#47212a", "review_soft": "#493918", "pending_soft": "#1c293b",
}
LIGHT = {
    "bg": "#e9eef5", "surface": "#ffffff", "surface2": "#f3f6fa", "border": "#c8d2df",
    "text": "#132033", "muted": "#627086", "accent": "#245fc7", "accent_hover": "#184da8",
    "live": "#087f57", "warning": "#a96400", "danger": "#bd3043", "video": "#0c1118",
    "timeline": "#e7edf5", "tick": "#66758a", "selection": "#c5d9fb",
    "valid_soft": "#dcefe7", "foul_soft": "#f7dfe3", "review_soft": "#fff0c9", "pending_soft": "#edf2f8",
}


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
        self.palette = DARK
        self.name = "dark"
        self._image_assets: dict[str, tk.PhotoImage] = {}
        self._popup_binding_installed = False

    def _checkbox_image(self, key: str, border: str, fill: str, checked: bool) -> tk.PhotoImage:
        image = tk.PhotoImage(master=self.root, width=22, height=22)
        for x0, y0, x1, y1 in ((6, 1, 16, 3), (3, 3, 19, 5), (1, 6, 21, 16), (3, 17, 19, 19), (6, 19, 16, 21)):
            image.put(border, to=(x0, y0, x1, y1))
        image.put(border, to=(1, 6, 3, 16)); image.put(border, to=(19, 6, 21, 16))
        for x0, y0, x1, y1 in ((6, 5, 16, 6), (5, 6, 17, 16), (6, 16, 16, 17)):
            image.put(fill, to=(x0, y0, x1, y1))
        if checked:
            for x, y in ((5, 9), (6, 10), (7, 11), (8, 12), (9, 13), (10, 12), (11, 11), (12, 10), (13, 9), (14, 8), (15, 7)):
                image.put("#ffffff", to=(x, y, x + 3, y + 3))
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

    def _rounded_image(self, key: str, fill: str, border: str, radius: int = 7) -> tk.PhotoImage:
        # This is a scalable nine-slice background, not the final control size.
        # Keep its centre compact so rounding does not inflate every button.
        width, height = 32, 20
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
                border=(7, 7, 7, 7), sticky="nswe",
            )
        style.layout(style_name, [(element, {"sticky": "nswe", "children": [
            ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]}),
        ]})])

    def _install_rounded_controls(self, style: ttk.Style, p: dict[str, str]) -> None:
        roles = {
            "neutral": (p["surface2"], p["selection"], p["border"]),
            "accent": (p["accent"], p["accent_hover"], p["accent"]),
            "live": (p["live"], p["live"], p["live"]),
            "warning": (p["warning"], p["warning"], p["warning"]),
            "danger": (p["danger"], p["danger"], p["danger"]),
        }
        assignments = {
            "TButton": "neutral", "Control.TButton": "neutral", "Sidebar.TButton": "neutral", "SettingsNav.TButton": "neutral",
            "Accent.TButton": "accent", "PrimaryJudge.TButton": "accent",
            "Live.TButton": "live", "LiveJudge.TButton": "live", "SystemResume.TButton": "live", "Valid.TButton": "live", "JudgeValid.TButton": "live",
            "SystemPause.TButton": "warning", "Review.TButton": "warning", "JudgeReview.TButton": "warning",
            "Danger.TButton": "danger", "Foul.TButton": "danger", "JudgeFoul.TButton": "danger",
        }
        for style_name, role in assignments.items():
            self._install_rounded_button_style(style, style_name, role, *roles[role])

        neutral_element = f"Modern{self.name.title()}.neutral.Button.background"
        for style_name in ("TMenubutton", "Header.TMenubutton"):
            style.layout(style_name, [(neutral_element, {"sticky": "nswe", "children": [
                ("Menubutton.padding", {"sticky": "nswe", "children": [
                    ("Menubutton.label", {"side": "left", "sticky": "nswe"}),
                    ("Menubutton.indicator", {"side": "right", "sticky": "e"}),
                ]}),
            ]})])

        combo_prefix = f"Modern{self.name.title()}.Combo"
        combo_element = f"{combo_prefix}.field"
        if combo_element not in style.element_names():
            combo_normal = self._rounded_image(f"{combo_prefix}.normal", p["surface2"], p["border"])
            combo_focus = self._rounded_image(f"{combo_prefix}.focus", p["surface2"], p["accent"])
            combo_disabled = self._rounded_image(f"{combo_prefix}.disabled", p["surface"], p["border"])
            style.element_create(
                combo_element, "image", combo_normal,
                ("disabled", combo_disabled), ("focus", combo_focus), ("active", combo_focus),
                border=(10, 10, 10, 10), sticky="nswe",
            )
        style.layout("TCombobox", [(combo_element, {"sticky": "nswe", "children": [
            ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
            ("Combobox.padding", {"expand": "1", "sticky": "nswe", "children": [
                ("Combobox.textarea", {"sticky": "nswe"}),
            ]}),
        ]})])

        if not self._popup_binding_installed:
            self.root.bind_class("TCombobox", "<ButtonPress-1>", self._round_combobox_popup, add="+")
            self._popup_binding_installed = True

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
                font=("Segoe UI", 10), borderwidth=1, relief="solid", activeborderwidth=0,
            )
        except tk.TclError:
            pass
        menu.bind("<Map>", lambda _event, m=menu: self._round_widget_window(m), add="+")

    def apply(self, requested: str) -> dict[str, str]:
        name = "dark" if requested == "dark" or (requested == "system" and system_prefers_dark()) else "light"
        self.name = name
        self.palette = DARK if name == "dark" else LIGHT
        p = self.palette
        self.root.configure(background=p["bg"])
        style = ttk.Style(self.root)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure(".", background=p["bg"], foreground=p["text"], fieldbackground=p["surface2"], bordercolor=p["border"], lightcolor=p["border"], darkcolor=p["border"], font=("Segoe UI", 9))
        style.configure("App.TFrame", background=p["bg"])
        style.configure("Panel.TFrame", background=p["surface"])
        style.configure("Toolbar.TFrame", background=p["surface2"])
        style.configure("JudgeHeader.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("ControlDock.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("Brand.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 15))
        style.configure("BrandSub.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("TButton", padding=(8, 0))
        style.configure("TMenubutton", background=p["surface2"], foreground=p["text"], padding=(10, 0), borderwidth=1, relief="flat", arrowcolor=p["muted"])
        style.map("TMenubutton", background=[("active", p["selection"]), ("pressed", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"])], arrowcolor=[("active", p["text"])])
        style.configure("Header.TMenubutton", background=p["surface2"], foreground=p["text"], padding=(11, 0), borderwidth=1, relief="flat", arrowcolor=p["muted"])
        style.map("Header.TMenubutton", background=[("active", p["selection"]), ("pressed", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"])], arrowcolor=[("active", p["text"])])
        style.configure("ContextTitle.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 8))
        style.configure("ContextValue.TLabel", background=p["surface2"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI Semibold", 14))
        style.configure("PanelTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 9))
        style.configure("Text.TLabel", background=p["surface"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["surface"], foreground=p["muted"])
        style.configure("Warning.TLabel", background=p["surface"], foreground=p["warning"])
        style.configure("HeaderMuted.TLabel", background=p["bg"], foreground=p["muted"])
        style.configure("Status.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("Control.TButton", padding=(9, 0), font=("Segoe UI", 9))
        style.map("Control.TButton", background=[("active", p["surface2"]), ("pressed", p["selection"])])
        style.configure("Accent.TButton", padding=(11, 0), font=("Segoe UI Semibold", 9), background=p["accent"], foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])])
        style.configure("Live.TButton", padding=(11, 0), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("PrimaryJudge.TButton", padding=(18, 4), font=("Segoe UI Semibold", 11), background=p["accent"], foreground="#ffffff")
        style.map("PrimaryJudge.TButton", background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])])
        style.configure("LiveJudge.TButton", padding=(14, 4), font=("Segoe UI Semibold", 10), background=p["live"], foreground="#ffffff")
        style.configure("Danger.TButton", padding=(9, 0), background=p["danger"], foreground="#ffffff")
        style.configure("SystemPause.TButton", padding=(12, 0), background=p["warning"], foreground="#111111", font=("Segoe UI Semibold", 9))
        style.configure("SystemResume.TButton", padding=(12, 0), background=p["live"], foreground="#ffffff", font=("Segoe UI Semibold", 9))
        style.configure("Valid.TButton", padding=(12, 0), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("Foul.TButton", padding=(12, 0), font=("Segoe UI Semibold", 9), background=p["danger"], foreground="#ffffff")
        style.configure("Review.TButton", padding=(12, 0), font=("Segoe UI Semibold", 9), background=p["warning"], foreground="#111111")
        style.configure("JudgeValid.TButton", padding=(16, 3), font=("Segoe UI Semibold", 10), background=p["live"], foreground="#ffffff")
        style.configure("JudgeFoul.TButton", padding=(16, 3), font=("Segoe UI Semibold", 10), background=p["danger"], foreground="#ffffff")
        style.configure("JudgeReview.TButton", padding=(16, 3), font=("Segoe UI Semibold", 10), background=p["warning"], foreground="#111111")
        style.configure("Sidebar.TButton", padding=(12, 2), anchor="w", background=p["surface2"], foreground=p["text"])
        style.map("Sidebar.TButton", background=[("active", p["selection"]), ("pressed", p["selection"])])
        style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"], rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 8), relief="flat")
        style.map("Treeview", background=[("selected", p["selection"])], foreground=[("selected", p["text"])])
        style.configure("TPanedwindow", background=p["border"], sashwidth=5)
        style.configure("TNotebook", background=p["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 7), background=p["surface2"], foreground=p["muted"])
        style.map("TNotebook.Tab", background=[("selected", p["surface"])], foreground=[("selected", p["text"])])
        style.configure("TCheckbutton", background=p["surface"], foreground=p["text"], padding=(2, 3), indicatorsize=20, indicatormargin=(0, 0, 7, 0))
        style.map("TCheckbutton", background=[("active", p["surface"])], foreground=[("disabled", p["muted"]), ("active", p["text"])])
        self._install_checkbox_style(style, p)
        style.configure("TRadiobutton", background=p["surface"], foreground=p["text"])
        style.configure("TEntry", fieldbackground=p["surface2"], foreground=p["text"], insertcolor=p["text"])
        style.map("TEntry", fieldbackground=[("disabled", p["surface"]), ("readonly", p["surface2"])], foreground=[("disabled", p["muted"])])
        style.configure("TSpinbox", fieldbackground=p["surface2"], foreground=p["text"], arrowcolor=p["text"], insertcolor=p["text"])
        style.map("TSpinbox", fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])], foreground=[("readonly", p["text"]), ("disabled", p["muted"])])
        style.configure("TCombobox", fieldbackground=p["surface2"], foreground=p["text"], arrowcolor=p["muted"], selectbackground=p["selection"], selectforeground=p["text"], padding=(9, 0), borderwidth=1, relief="flat", arrowsize=15)
        style.map("TCombobox", fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])], foreground=[("readonly", p["text"]), ("disabled", p["muted"])], bordercolor=[("focus", p["accent"]), ("active", p["accent"]), ("readonly", p["border"])], arrowcolor=[("active", p["text"]), ("readonly", p["muted"])], selectbackground=[("readonly", p["surface2"])], selectforeground=[("readonly", p["text"])])
        style.configure("Vertical.TScrollbar", background=p["surface2"], troughcolor=p["bg"], arrowcolor=p["text"])
        style.configure("Horizontal.TScrollbar", background=p["surface2"], troughcolor=p["bg"], arrowcolor=p["text"])
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
        style.configure("SettingsRow.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("SettingsRowTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("SettingsRowDesc.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("SettingsSection.TLabelframe", background=p["surface"], bordercolor=p["border"], relief="solid", borderwidth=1)
        style.configure("SettingsSection.TLabelframe.Label", background=p["surface"], foreground=p["muted"], font=("Segoe UI Semibold", 9))
        style.configure("SettingsNav.TButton", padding=(14, 3), anchor="w", background=p["surface2"], foreground=p["muted"], borderwidth=0)
        style.map("SettingsNav.TButton", background=[("active", p["selection"]), ("pressed", p["selection"]), ("selected", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"]), ("selected", p["text"])])
        self._install_rounded_controls(style, p)
        # ttk combobox pop-downs use a classic Tk Listbox on Windows.
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
