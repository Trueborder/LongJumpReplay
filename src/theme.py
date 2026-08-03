from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk


DARK = {
    "bg": "#0c0f14", "surface": "#121720", "surface2": "#181f2b", "border": "#293241",
    "text": "#eef2f7", "muted": "#99a4b3", "accent": "#4f8cff", "accent_hover": "#70a2ff",
    "live": "#42d392", "warning": "#f6c85f", "danger": "#ff6b6b", "video": "#05070a",
    "timeline": "#151b25", "tick": "#738096", "selection": "#284a7a",
    "valid_soft": "#16392c", "foul_soft": "#452328", "review_soft": "#493c1b", "pending_soft": "#202b3a",
}
LIGHT = {
    "bg": "#eef1f5", "surface": "#ffffff", "surface2": "#f6f8fb", "border": "#ced5df",
    "text": "#17202c", "muted": "#667386", "accent": "#2867d9", "accent_hover": "#1f55b5",
    "live": "#138a5b", "warning": "#b16b00", "danger": "#c43b3b", "video": "#111317",
    "timeline": "#e5e9ef", "tick": "#677386", "selection": "#b9d3ff",
    "valid_soft": "#dff3e9", "foul_soft": "#f8e2e2", "review_soft": "#fff2cf", "pending_soft": "#edf1f6",
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
        style.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI Semibold", 14))
        style.configure("PanelTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 9))
        style.configure("Text.TLabel", background=p["surface"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["surface"], foreground=p["muted"])
        style.configure("HeaderMuted.TLabel", background=p["bg"], foreground=p["muted"])
        style.configure("Status.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("Control.TButton", padding=(9, 6), font=("Segoe UI", 9))
        style.map("Control.TButton", background=[("active", p["surface2"]), ("pressed", p["selection"])])
        style.configure("Accent.TButton", padding=(11, 6), font=("Segoe UI Semibold", 9), background=p["accent"], foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])])
        style.configure("Live.TButton", padding=(11, 6), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("Danger.TButton", padding=(9, 6), background=p["danger"], foreground="#ffffff")
        style.configure("Valid.TButton", padding=(12, 7), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("Foul.TButton", padding=(12, 7), font=("Segoe UI Semibold", 9), background=p["danger"], foreground="#ffffff")
        style.configure("Review.TButton", padding=(12, 7), font=("Segoe UI Semibold", 9), background=p["warning"], foreground="#111111")
        style.configure("Sidebar.TButton", padding=(12, 9), anchor="w", background=p["surface2"], foreground=p["text"])
        style.map("Sidebar.TButton", background=[("active", p["selection"]), ("pressed", p["selection"])])
        style.configure("Treeview", background=p["surface"], fieldbackground=p["surface"], foreground=p["text"], rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 8), relief="flat")
        style.map("Treeview", background=[("selected", p["selection"])], foreground=[("selected", p["text"])])
        style.configure("TPanedwindow", background=p["border"], sashwidth=5)
        style.configure("TNotebook", background=p["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 7), background=p["surface2"], foreground=p["muted"])
        style.map("TNotebook.Tab", background=[("selected", p["surface"])], foreground=[("selected", p["text"])])
        style.configure("TCheckbutton", background=p["surface"], foreground=p["text"])
        style.configure("TRadiobutton", background=p["surface"], foreground=p["text"])
        style.configure("TEntry", fieldbackground=p["surface2"], foreground=p["text"], insertcolor=p["text"])
        style.map("TEntry", fieldbackground=[("disabled", p["surface"]), ("readonly", p["surface2"])], foreground=[("disabled", p["muted"])])
        style.configure("TSpinbox", fieldbackground=p["surface2"], foreground=p["text"], arrowcolor=p["text"], insertcolor=p["text"])
        style.map("TSpinbox", fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])], foreground=[("readonly", p["text"]), ("disabled", p["muted"])])
        style.configure("TCombobox", fieldbackground=p["surface2"], foreground=p["text"], arrowcolor=p["text"], selectbackground=p["selection"], selectforeground=p["text"])
        style.map("TCombobox", fieldbackground=[("readonly", p["surface2"]), ("disabled", p["surface"])], foreground=[("readonly", p["text"]), ("disabled", p["muted"])], selectbackground=[("readonly", p["selection"])], selectforeground=[("readonly", p["text"])])
        style.configure("Vertical.TScrollbar", background=p["surface2"], troughcolor=p["bg"], arrowcolor=p["text"])
        style.configure("Horizontal.TScrollbar", background=p["surface2"], troughcolor=p["bg"], arrowcolor=p["text"])
        style.configure("ImpactLow.TLabel", background=p["surface"], foreground=p["live"], font=("Segoe UI Semibold", 8))
        style.configure("ImpactMedium.TLabel", background=p["surface"], foreground=p["warning"], font=("Segoe UI Semibold", 8))
        style.configure("ImpactHigh.TLabel", background=p["surface"], foreground=p["danger"], font=("Segoe UI Semibold", 8))
        style.configure("ImpactVeryHigh.TLabel", background=p["surface"], foreground=p["danger"], font=("Segoe UI Semibold", 8, "underline"))
        style.configure("ImpactNone.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("SettingsNav.TButton", padding=(12, 8), anchor="w", background=p["surface2"], foreground=p["text"])
        style.map("SettingsNav.TButton", background=[("active", p["selection"]), ("pressed", p["selection"])])
        # ttk combobox pop-downs use a classic Tk Listbox on Windows.
        self.root.option_add("*TCombobox*Listbox.background", p["surface2"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["selection"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["text"])
        self.root.option_add("*Listbox.background", p["surface2"])
        self.root.option_add("*Listbox.foreground", p["text"])
        self.root.option_add("*Listbox.selectBackground", p["selection"])
        self.root.option_add("*Listbox.selectForeground", p["text"])
        return p
