from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk


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
        style.configure("Header.TMenubutton", background=p["surface"], foreground=p["muted"], padding=(9, 5), borderwidth=0)
        style.map("Header.TMenubutton", background=[("active", p["surface2"]), ("pressed", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"])])
        style.configure("ContextTitle.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 8))
        style.configure("ContextValue.TLabel", background=p["surface2"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI Semibold", 14))
        style.configure("PanelTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 9))
        style.configure("Text.TLabel", background=p["surface"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["surface"], foreground=p["muted"])
        style.configure("Warning.TLabel", background=p["surface"], foreground=p["warning"])
        style.configure("HeaderMuted.TLabel", background=p["bg"], foreground=p["muted"])
        style.configure("Status.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("Control.TButton", padding=(9, 6), font=("Segoe UI", 9))
        style.map("Control.TButton", background=[("active", p["surface2"]), ("pressed", p["selection"])])
        style.configure("Accent.TButton", padding=(11, 6), font=("Segoe UI Semibold", 9), background=p["accent"], foreground="#ffffff")
        style.map("Accent.TButton", background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])])
        style.configure("Live.TButton", padding=(11, 6), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("PrimaryJudge.TButton", padding=(18, 11), font=("Segoe UI Semibold", 11), background=p["accent"], foreground="#ffffff")
        style.map("PrimaryJudge.TButton", background=[("active", p["accent_hover"]), ("pressed", p["accent_hover"])])
        style.configure("LiveJudge.TButton", padding=(14, 11), font=("Segoe UI Semibold", 10), background=p["live"], foreground="#ffffff")
        style.configure("Danger.TButton", padding=(9, 6), background=p["danger"], foreground="#ffffff")
        style.configure("SystemPause.TButton", padding=(12, 7), background=p["warning"], foreground="#111111", font=("Segoe UI Semibold", 9))
        style.configure("SystemResume.TButton", padding=(12, 7), background=p["live"], foreground="#ffffff", font=("Segoe UI Semibold", 9))
        style.configure("Valid.TButton", padding=(12, 7), font=("Segoe UI Semibold", 9), background=p["live"], foreground="#ffffff")
        style.configure("Foul.TButton", padding=(12, 7), font=("Segoe UI Semibold", 9), background=p["danger"], foreground="#ffffff")
        style.configure("Review.TButton", padding=(12, 7), font=("Segoe UI Semibold", 9), background=p["warning"], foreground="#111111")
        style.configure("JudgeValid.TButton", padding=(16, 10), font=("Segoe UI Semibold", 10), background=p["live"], foreground="#ffffff")
        style.configure("JudgeFoul.TButton", padding=(16, 10), font=("Segoe UI Semibold", 10), background=p["danger"], foreground="#ffffff")
        style.configure("JudgeReview.TButton", padding=(16, 10), font=("Segoe UI Semibold", 10), background=p["warning"], foreground="#111111")
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
        style.configure("SettingsHeader.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("SettingsSidebar.TFrame", background=p["surface2"], borderwidth=1, relief="solid")
        style.configure("SettingsHero.TFrame", background=p["surface2"], borderwidth=1, relief="solid")
        style.configure("SettingsHeroTitle.TLabel", background=p["surface2"], foreground=p["text"], font=("Segoe UI Semibold", 18))
        style.configure("SettingsHeroDesc.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("SettingsGroup.TLabel", background=p["surface2"], foreground=p["muted"], font=("Segoe UI Semibold", 8))
        style.configure("SettingsDirty.TLabel", background=p["surface"], foreground=p["warning"], font=("Segoe UI Semibold", 8))
        style.configure("SettingsRow.TFrame", background=p["surface"], borderwidth=1, relief="solid")
        style.configure("SettingsRowTitle.TLabel", background=p["surface"], foreground=p["text"], font=("Segoe UI Semibold", 10))
        style.configure("SettingsRowDesc.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        style.configure("SettingsSection.TLabelframe", background=p["surface"], bordercolor=p["border"], relief="solid", borderwidth=1)
        style.configure("SettingsSection.TLabelframe.Label", background=p["surface"], foreground=p["muted"], font=("Segoe UI Semibold", 9))
        style.configure("SettingsNav.TButton", padding=(14, 9), anchor="w", background=p["surface2"], foreground=p["muted"], borderwidth=0)
        style.map("SettingsNav.TButton", background=[("active", p["selection"]), ("pressed", p["selection"]), ("selected", p["selection"])], foreground=[("active", p["text"]), ("pressed", p["text"]), ("selected", p["text"])])
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
