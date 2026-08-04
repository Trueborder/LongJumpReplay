from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import messagebox, ttk
from collections.abc import Callable

from .config import AppConfig, DEFAULT_HOTKEYS, PERFORMANCE_PRESETS, apply_low_resource_mode, apply_performance_preset
from .camera_devices import enumerate_camera_devices
from .hotkeys import event_to_hotkey
from .i18n import Translator


ACTION_LABELS = {
    "freeze_toggle": ("Freeze / return to live", "Zmrazit / návrat živě"),
    "return_live": ("Return to live", "Návrat živě"),
    "previous_frame": ("Previous frame", "Předchozí snímek"),
    "next_frame": ("Next frame", "Následující snímek"),
    "previous_attempt": ("Previous recording", "Předchozí záznam"),
    "next_attempt": ("Next recording", "Následující záznam"),
    "previous_athlete": ("Previous athlete", "Předchozí závodník"),
    "next_athlete": ("Next athlete", "Další závodník"),
    "decision_not_decided": ("Mark Not decided", "Označit Nerozhodnuto"),
    "decision_valid": ("Mark valid", "Označit platný"),
    "decision_foul": ("Mark foul", "Označit přešlap"),
    "decision_review": ("Mark for review", "Označit ke kontrole"),
    "mark_passed": ("Mark passed", "Označit vynecháno"),
    "add_marker": ("Add marker", "Přidat značku"),
    "save_frame": ("Save current frame", "Uložit aktuální snímek"),
    "export_attempt": ("Export recording", "Exportovat záznam"),
    "clear_all_recordings": ("Clear temporary recordings", "Vymazat dočasné záznamy"),
    "toggle_attempts": ("Show / hide recordings", "Zobrazit / skrýt záznamy"),
    "toggle_competition_board": ("Show / hide competition board", "Zobrazit / skrýt tabulku"),
    "toggle_timeline": ("Show / hide timeline", "Zobrazit / skrýt časovou osu"),
    "toggle_live_preview": ("Show / hide live preview", "Zobrazit / skrýt živý náhled"),
    "toggle_fullscreen": ("Toggle fullscreen", "Celá obrazovka"),
    "reset_view": ("Reset video zoom", "Obnovit zoom videa"),
    "toggle_guide": ("Show / hide board guide", "Zobrazit / skrýt čáru"),
    "toggle_comparison": ("Toggle three-frame comparison", "Přepnout porovnání snímků"),
    "start_competition_wizard": ("Start Competition Wizard", "Spustit průvodce soutěží"),
    "timer_toggle": ("", ""),  # Label is localized through src/i18n.py.
}

SHUTTLE_ACTIONS = [
    "freeze_toggle", "return_live", "decision_not_decided", "decision_valid", "decision_foul",
    "decision_review", "previous_athlete", "next_athlete", "mark_passed", "add_marker",
    "save_frame", "export_attempt", "none",
]

IMPACT_STYLES = {
    "none": "ImpactNone.TLabel",
    "low": "ImpactLow.TLabel",
    "medium": "ImpactMedium.TLabel",
    "high": "ImpactHigh.TLabel",
    "very_high": "ImpactVeryHigh.TLabel",
}


class SettingsDialog(tk.Toplevel):
    """Scrollable category settings with a fixed action footer."""

    CATEGORY_DEFS = [
        ("general", "General", "Obecné"),
        ("appearance", "Language & appearance", "Jazyk a vzhled"),
        ("performance", "Performance", "Výkon"),
        ("camera", "Camera", "Kamera"),
        ("board", "Board calibration", "Kalibrace prkna"),
        ("competition", "Competition", "Soutěž"),
        ("rounds", "Athletes & rounds", "Závodníci a kola"),
        ("decisions", "Attempts & decisions", "Pokusy a rozhodnutí"),
        ("final", "Final round", "Finále"),
        ("replay", "Replay & storage", "Replay a úložiště"),
        ("views", "Views", "Pohledy"),
        ("assist", "Take-off Assist", "Asistent odrazu"),
        ("hotkeys", "Hotkeys", "Klávesové zkratky"),
        ("shuttle", "ShuttleXpress", "ShuttleXpress"),
        ("recovery", "Recovery & export", "Obnova a export"),
        ("advanced", "Advanced", "Pokročilé"),
    ]
    CATEGORY_GROUPS = [
        ("essentials", "ESSENTIALS", "ZÁKLADNÍ", ("general", "appearance", "camera")),
        ("judging", "JUDGING WORKFLOW", "ROZHODOVÁNÍ", ("competition", "rounds", "decisions", "final")),
        ("replay", "REPLAY WORKSPACE", "PRACOVNÍ PLOCHA", ("board", "replay", "views", "assist")),
        ("system", "CONTROLS & SYSTEM", "OVLÁDÁNÍ A SYSTÉM", ("hotkeys", "shuttle", "performance", "recovery", "advanced")),
    ]

    def __init__(
        self,
        parent: tk.Misc,
        config: AppConfig,
        on_apply: Callable[[AppConfig], None],
        on_camera_diagnostic: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.working = deepcopy(config)
        self.on_apply = on_apply
        self.on_camera_diagnostic = on_camera_diagnostic
        self.lang = self.working.general.language
        self.tr = Translator(self.lang)
        self.title(self.tr("settings.title"))
        self.geometry("1220x820")
        self.minsize(1100, 700)
        self.transient(parent)
        self.grab_set()
        self._vars: dict[str, tk.Variable] = {}
        self._pages: dict[str, ttk.Frame] = {}
        self._page_inners: dict[str, ttk.Frame] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._nav_group_labels: dict[str, ttk.Label] = {}
        self._category_group: dict[str, str] = {}
        self._current_page = ""
        self._dirty = False
        self._initialising = True
        self.hotkey_tree: ttk.Treeview | None = None
        self.roster_tree: ttk.Treeview | None = None
        self.shuttle_vars: dict[int, tk.StringVar] = {}
        self._setting_rows: list[tuple[ttk.Frame, tk.Widget, ttk.Label | None]] = []
        self._build()
        self._initialising = False
        self._attach_dirty_traces()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._show_page("general")

    def _txt(self, en: str, cs: str) -> str:
        return cs if self.lang == "cs" else en

    def _action_label(self, action: str) -> str:
        if action == "timer_toggle":
            return self.tr("settings.athlete_timer_hotkey")
        values = ACTION_LABELS.get(action, (action, action))
        return values[1] if self.lang == "cs" else values[0]

    def _build(self) -> None:
        shell = ttk.Frame(self, style="App.TFrame", padding=14)
        shell.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)
        shell.columnconfigure(0, weight=1)

        header = ttk.Frame(shell, style="SettingsHeader.TFrame", padding=(18, 13))
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        brand = ttk.Frame(header, style="Panel.TFrame")
        brand.pack(side="left")
        ttk.Label(brand, text=self.tr("settings.header"), style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text=self.tr("settings.subtitle"), style="Muted.TLabel").pack(anchor="w", pady=(1, 0))
        self.dirty_label = ttk.Label(header, text="", style="SettingsDirty.TLabel")
        self.dirty_label.pack(side="right", padx=(14, 0))

        body = ttk.Frame(shell, style="App.TFrame")
        body.grid(row=1, column=0, sticky="nsew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        sidebar = ttk.Frame(body, style="SettingsSidebar.TFrame", padding=10, width=255)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        sidebar.grid_propagate(False)
        ttk.Label(sidebar, text=self.tr("settings.find_area"), style="SettingsGroup.TLabel").pack(anchor="w", padx=5, pady=(2, 5))
        self.search_var = tk.StringVar()
        search = ttk.Entry(sidebar, textvariable=self.search_var)
        search.pack(fill="x", pady=(0, 10))
        search.insert(0, "")
        self.nav_host = ttk.Frame(sidebar, style="Toolbar.TFrame")
        self.nav_host.pack(fill="both", expand=True)

        self.page_host = ttk.Frame(body, style="Panel.TFrame", padding=1)
        self.page_host.grid(row=0, column=1, sticky="nsew")
        definitions = {key: (en, cs) for key, en, cs in self.CATEGORY_DEFS}
        for group_key, group_en, group_cs, keys in self.CATEGORY_GROUPS:
            label = ttk.Label(self.nav_host, text=self._txt(group_en, group_cs), style="SettingsGroup.TLabel")
            label.pack(fill="x", padx=5, pady=(10 if self._nav_group_labels else 2, 4))
            self._nav_group_labels[group_key] = label
            for key in keys:
                en, cs = definitions[key]
                self._category_group[key] = group_key
                button = ttk.Button(self.nav_host, text=self._txt(en, cs), style="SettingsNav.TButton", command=lambda k=key: self._show_page(k))
                button.pack(fill="x", pady=1)
                self._nav_buttons[key] = button
        for key, _en, _cs in self.CATEGORY_DEFS:
            wrapper, inner = self._new_scroll_page()
            self._pages[key] = wrapper
            self._page_inners[key] = inner

        self.search_var.trace_add("write", lambda *_: self._filter_navigation())
        self._build_general(self._page_inners["general"])
        self._build_appearance(self._page_inners["appearance"])
        self._build_performance(self._page_inners["performance"])
        self._build_camera(self._page_inners["camera"])
        self._build_board(self._page_inners["board"])
        self._build_competition(self._page_inners["competition"])
        self._build_rounds(self._page_inners["rounds"])
        self._build_decisions(self._page_inners["decisions"])
        self._build_final(self._page_inners["final"])
        self._build_replay(self._page_inners["replay"])
        self._build_views(self._page_inners["views"])
        self._build_assist(self._page_inners["assist"])
        self._build_hotkeys(self._page_inners["hotkeys"])
        self._build_shuttle(self._page_inners["shuttle"])
        self._build_recovery(self._page_inners["recovery"])
        self._build_advanced(self._page_inners["advanced"])

        footer = ttk.Frame(shell, style="SettingsHeader.TFrame", padding=(12, 9))
        self.footer = footer
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.restore_button = ttk.Button(footer, text=self.tr("settings.restore"), style="Control.TButton", command=self._restore_defaults)
        self.restore_button.pack(side="left")
        self.cancel_button = ttk.Button(footer, text=self.tr("settings.cancel"), style="Control.TButton", command=self._cancel)
        self.cancel_button.pack(side="right")
        self.apply_close_button = ttk.Button(footer, text=self.tr("settings.apply_close"), style="Accent.TButton", command=lambda: self._apply(True))
        self.apply_close_button.pack(side="right", padx=(0, 7))
        self.apply_button = ttk.Button(footer, text=self.tr("settings.apply"), style="Control.TButton", command=lambda: self._apply(False))
        self.apply_button.pack(side="right", padx=(0, 7))

    def _new_scroll_page(self) -> tuple[ttk.Frame, ttk.Frame]:
        wrapper = ttk.Frame(self.page_host, style="Panel.TFrame")
        panel_bg = ttk.Style(self).lookup("Panel.TFrame", "background") or self.cget("background")
        canvas = tk.Canvas(wrapper, highlightthickness=0, bd=0, background=panel_bg)
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        inner = ttk.Frame(canvas, style="Panel.TFrame", padding=18)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.bind("<Configure>", lambda e, c=canvas, w=window: c.itemconfigure(w, width=e.width))
        canvas.bind("<MouseWheel>", lambda e, c=canvas: (c.yview_scroll(-1 if e.delta > 0 else 1, "units"), "break")[1])
        return wrapper, inner

    def _show_page(self, key: str) -> None:
        if key == self._current_page:
            return
        if self._current_page:
            self._pages[self._current_page].pack_forget()
        self._pages[key].pack(fill="both", expand=True)
        self._current_page = key
        for name, button in self._nav_buttons.items():
            button.state(["selected"] if name == key else ["!selected"])

    def _filter_navigation(self) -> None:
        query = self.search_var.get().strip().lower()
        definitions = {key: (en, cs) for key, en, cs in self.CATEGORY_DEFS}
        visible_keys: list[str] = []
        for label in self._nav_group_labels.values():
            label.pack_forget()
        for button in self._nav_buttons.values():
            button.pack_forget()
        for group_key, _en, _cs, keys in self.CATEGORY_GROUPS:
            matches = [key for key in keys if not query or query in definitions[key][0].lower() or query in definitions[key][1].lower()]
            if not matches:
                continue
            self._nav_group_labels[group_key].pack(fill="x", padx=5, pady=(10 if visible_keys else 2, 4))
            for key in matches:
                self._nav_buttons[key].pack(fill="x", pady=1)
                visible_keys.append(key)
        first = visible_keys[0] if visible_keys else None
        if first and self._current_page not in visible_keys:
            self._show_page(first)

    def _title(self, frame: ttk.Frame, title_en: str, title_cs: str, desc_en: str = "", desc_cs: str = "") -> int:
        hero = ttk.Frame(frame, style="SettingsHero.TFrame", padding=(18, 15))
        hero.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        ttk.Label(hero, text=self._txt(title_en, title_cs), style="SettingsHeroTitle.TLabel").pack(anchor="w")
        if desc_en or desc_cs:
            ttk.Label(hero, text=self._txt(desc_en, desc_cs), style="SettingsHeroDesc.TLabel", wraplength=780, justify="left").pack(anchor="w", pady=(5, 0))
        columns = ttk.Frame(frame, style="SettingsGroup.TFrame", padding=(14, 5))
        columns.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 2))
        self._configure_row_columns(columns)
        ttk.Label(columns, text=self.tr("settings.column.option"), style="SettingsGroup.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(columns, text=self.tr("settings.column.description"), style="SettingsGroup.TLabel").grid(row=0, column=1, sticky="w", padx=(18, 18))
        ttk.Label(columns, text=self.tr("settings.column.value"), style="SettingsGroup.TLabel").grid(row=0, column=2, sticky="w")
        frame.columnconfigure(0, weight=1)
        return 2

    @staticmethod
    def _configure_row_columns(container: ttk.Frame) -> None:
        container.columnconfigure(0, minsize=220, weight=0)
        container.columnconfigure(1, minsize=300, weight=1)
        container.columnconfigure(2, minsize=210, weight=0)

    def _impact_text(self, impact: str) -> str:
        return self.tr(f"settings.impact.{impact}")

    def _row(
        self,
        frame: ttk.Frame,
        row: int,
        label_en: str,
        label_cs: str,
        var: tk.Variable,
        kind: str = "entry",
        values: tuple[str, ...] = (),
        desc_en: str = "",
        desc_cs: str = "",
        impact: str = "none",
        width: int | None = None,
    ) -> tk.Widget:
        card = ttk.Frame(frame, style="SettingsRow.TFrame", padding=(14, 11))
        card.grid(row=row, column=0, columnspan=4, sticky="ew", pady=4)
        self._configure_row_columns(card)
        left = ttk.Frame(card, style="Panel.TFrame")
        left.grid(row=0, column=0, sticky="nw")
        ttk.Label(left, text=self._txt(label_en, label_cs), style="SettingsRowTitle.TLabel", wraplength=205, justify="left").pack(anchor="w")
        if impact != "none":
            ttk.Label(left, text=self._impact_text(impact), style=IMPACT_STYLES[impact]).pack(anchor="w", pady=(2, 0))
        if kind == "check":
            widget: tk.Widget = ttk.Checkbutton(card, variable=var)
        elif kind == "combo":
            widget = ttk.Combobox(card, textvariable=var, values=values, state="readonly", width=width)
        elif kind == "spin":
            widget = ttk.Spinbox(card, textvariable=var, from_=0, to=10000, increment=1, width=width)
        else:
            widget = ttk.Entry(card, textvariable=var, width=width)
        description: ttk.Label | None = None
        if desc_en or desc_cs:
            description = ttk.Label(card, text=self._txt(desc_en, desc_cs), style="SettingsRowDesc.TLabel", wraplength=300, justify="left")
            description.grid(row=0, column=1, sticky="nw", padx=(18, 18))
        widget.grid(row=0, column=2, sticky="w" if kind == "check" else "ew")
        self._setting_rows.append((card, widget, description))
        return widget

    def _section(self, frame: ttk.Frame, row: int, title_en: str, title_cs: str) -> ttk.LabelFrame:
        box = ttk.LabelFrame(frame, text=self._txt(title_en, title_cs), padding=10, style="SettingsSection.TLabelframe")
        box.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 4))
        box.columnconfigure(1, weight=1)
        return box

    def _build_general(self, f: ttk.Frame) -> None:
        r = self._title(f, "General", "Obecné", "Basic application behaviour.", "Základní chování aplikace.")
        g = self.working.general
        self._vars["confirm_destructive"] = tk.BooleanVar(value=g.confirm_destructive_actions)
        self._vars["show_tooltips"] = tk.BooleanVar(value=g.show_tooltips)
        self._vars["fullscreen"] = tk.BooleanVar(value=self.working.display.fullscreen)
        self._vars["remember_geometry"] = tk.BooleanVar(value=self.working.display.remember_geometry)
        self._row(f, r, "Confirm destructive actions", "Potvrzovat mazání", self._vars["confirm_destructive"], "check", desc_en="Shows a confirmation before clearing or deleting recordings.", desc_cs="Před smazáním záznamů zobrazí potvrzení."); r += 1
        self._row(f, r, "Show setting descriptions", "Zobrazovat popisy nastavení", self._vars["show_tooltips"], "check"); r += 1
        self._row(f, r, "Start fullscreen", "Spustit přes celou obrazovku", self._vars["fullscreen"], "check", impact="low"); r += 1
        self._row(f, r, "Remember window and panel sizes", "Pamatovat velikost okna a panelů", self._vars["remember_geometry"], "check")

    def _build_appearance(self, f: ttk.Frame) -> None:
        r = self._title(f, "Language & appearance", "Jazyk a vzhled", "The language is applied to the main interface after Apply.", "Jazyk se na hlavní rozhraní použije po stisku Použít.")
        self._vars["language"] = tk.StringVar(value=self.working.general.language)
        self._vars["theme"] = tk.StringVar(value=self.working.display.theme)
        self._row(f, r, "Language", "Jazyk", self._vars["language"], "combo", ("en", "cs"), desc_en="English (en) or Czech (cs).", desc_cs="Angličtina (en) nebo čeština (cs)."); r += 1
        self._row(f, r, "Theme", "Motiv", self._vars["theme"], "combo", ("system", "dark", "light"), impact="low")

    def _build_performance(self, f: ttk.Frame) -> None:
        r = self._title(f, "Performance", "Výkon", "Presets reduce display work first. Recorded evidence quality is never silently reduced.", "Profily nejdříve snižují zátěž zobrazování. Kvalita důkazního exportu se nikdy nesníží potichu.")
        p = self.working.performance
        self._vars.update({
            "performance_preset": tk.StringVar(value=p.preset),
            "preview_hz": tk.IntVar(value=p.preview_refresh_hz),
            "timeline_hz": tk.IntVar(value=p.timeline_refresh_hz),
            "status_hz": tk.IntVar(value=p.status_refresh_hz),
            "attempts_hz": tk.IntVar(value=p.attempts_refresh_hz),
            "preview_scale": tk.DoubleVar(value=p.preview_scale),
            "pause_hidden": tk.BooleanVar(value=p.pause_hidden_panels),
            "reduce_minimized": tk.BooleanVar(value=p.reduce_when_minimized),
            "adaptive": tk.BooleanVar(value=p.adaptive_enabled),
            "menu_throttle": tk.BooleanVar(value=p.menu_throttle_enabled),
            "jpeg_quality": tk.IntVar(value=self.working.buffer.jpeg_quality),
        })
        preset_box = self._section(f, r, "Performance preset", "Výkonový profil"); r += 1
        ttk.Combobox(preset_box, textvariable=self._vars["performance_preset"], values=("quiet", "balanced", "high", "evidence", "custom"), state="readonly", width=22).grid(row=0, column=0, sticky="w")
        ttk.Button(preset_box, text=self._txt("Load preset", "Načíst profil"), command=self._load_performance_preset).grid(row=0, column=1, padx=(8, 0), sticky="w")
        ttk.Button(preset_box, text=self._txt("Older PC mode", "Režim pro slabší PC"), command=self._load_low_resource_mode).grid(row=0, column=2, padx=(8, 0), sticky="w")
        self.preset_description = ttk.Label(preset_box, style="Muted.TLabel", wraplength=650, justify="left")
        self.preset_description.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(
            preset_box,
            text=self._txt(
                "Older PC mode explicitly retains every second camera frame and needs an app restart.",
                "Režim pro slabší PC výslovně ukládá každý druhý snímek kamery a vyžaduje restart aplikace.",
            ),
            style="Warning.TLabel",
            wraplength=650,
            justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._vars["performance_preset"].trace_add("write", lambda *_: self._update_preset_description())
        self._update_preset_description()
        self._row(f, r, "Live/replay preview refresh", "Obnovování náhledu videa", self._vars["preview_hz"], desc_en="Changes interface smoothness, not camera recording FPS.", desc_cs="Mění plynulost rozhraní, ne snímkovou frekvenci záznamu kamery.", impact="high"); r += 1
        self._row(f, r, "Timeline refresh", "Obnovování časové osy", self._vars["timeline_hz"], impact="medium"); r += 1
        self._row(f, r, "Status refresh", "Obnovování stavů", self._vars["status_hz"], impact="low"); r += 1
        self._row(f, r, "Recordings/board refresh", "Obnovování záznamů a tabulky", self._vars["attempts_hz"], impact="low"); r += 1
        self._row(f, r, "Preview render scale", "Měřítko vykreslení náhledu", self._vars["preview_scale"], desc_en="0.75 lowers display workload; evidence remains full resolution.", desc_cs="0,75 sníží zátěž náhledu; důkaz zůstane v plném rozlišení.", impact="high"); r += 1
        self._row(f, r, "Pause hidden panels", "Pozastavit skryté panely", self._vars["pause_hidden"], "check", impact="medium"); r += 1
        self._row(f, r, "Reduce work when minimized", "Omezit zátěž při minimalizaci", self._vars["reduce_minimized"], "check", impact="high"); r += 1
        self._row(f, r, "Adaptive performance", "Adaptivní výkon", self._vars["adaptive"], "check", desc_en="Temporarily lowers preview refresh if the GUI or encoder queue falls behind.", desc_cs="Dočasně sníží obnovování náhledu, pokud se rozhraní nebo enkodér zpožďuje.", impact="medium"); r += 1
        self._row(f, r, "Throttle rendering while menus are open", "Omezit vykreslování při otevřeném menu", self._vars["menu_throttle"], "check", desc_en="Improves responsiveness of File/View/Help menus.", desc_cs="Zlepšuje odezvu nabídek Soubor/Zobrazení/Nápověda.", impact="medium"); r += 1
        self._row(f, r, "Live buffer JPEG quality", "Kvalita JPEG v živém bufferu", self._vars["jpeg_quality"], desc_en="Higher values use more CPU and RAM. Exported evidence PNG remains lossless.", desc_cs="Vyšší hodnoty využijí více CPU a RAM. Důkazní PNG zůstává bezeztrátové.", impact="very_high")

    def _update_preset_description(self) -> None:
        if not hasattr(self, "preset_description"):
            return
        preset = self._vars.get("performance_preset", tk.StringVar(value="balanced")).get()
        descriptions = {
            "quiet": self._txt("Lowest fan noise and CPU use. Best for webcams and older laptops.", "Nejnižší hluk ventilátoru a využití CPU. Vhodné pro webkamery a slabší notebooky."),
            "balanced": self._txt("Recommended default. Smooth controls without wasting CPU on invisible detail.", "Doporučené výchozí nastavení. Plynulé ovládání bez zbytečné spotřeby CPU."),
            "high": self._txt("Faster preview and seeking for powerful computers. Higher fan noise.", "Rychlejší náhled a posun pro výkonné počítače. Vyšší hluk ventilátoru."),
            "evidence": self._txt("Prioritises a full-resolution preview and higher-detail board analysis. Higher CPU use; buffer quality remains explicit.", "Upřednostňuje náhled v plném rozlišení a podrobnější analýzu prkna. Vyšší využití CPU; kvalita bufferu zůstává samostatnou volbou."),
            "custom": self._txt("Use the individual values below.", "Použije jednotlivé hodnoty níže."),
        }
        self.preset_description.configure(text=descriptions.get(preset, ""))

    def _load_performance_preset(self) -> None:
        preset = str(self._vars["performance_preset"].get())
        if preset == "custom":
            return
        temp = deepcopy(self.working)
        apply_performance_preset(temp, preset)
        p = temp.performance
        self._vars["preview_hz"].set(p.preview_refresh_hz)
        self._vars["timeline_hz"].set(p.timeline_refresh_hz)
        self._vars["status_hz"].set(p.status_refresh_hz)
        self._vars["attempts_hz"].set(p.attempts_refresh_hz)
        self._vars["preview_scale"].set(p.preview_scale)
        self._vars["pause_hidden"].set(p.pause_hidden_panels)
        self._vars["reduce_minimized"].set(p.reduce_when_minimized)
        self._vars["adaptive"].set(p.adaptive_enabled)
        self._vars["jpeg_quality"].set(temp.buffer.jpeg_quality)
        if "assist_width" in self._vars:
            self._vars["assist_width"].set(temp.takeoff_assist.downscale_width)

    def _load_low_resource_mode(self) -> None:
        temp = deepcopy(self.working)
        apply_low_resource_mode(temp)
        p, b = temp.performance, temp.buffer
        self._vars["performance_preset"].set(p.preset)
        self._vars["preview_hz"].set(p.preview_refresh_hz)
        self._vars["timeline_hz"].set(p.timeline_refresh_hz)
        self._vars["status_hz"].set(p.status_refresh_hz)
        self._vars["attempts_hz"].set(p.attempts_refresh_hz)
        self._vars["preview_scale"].set(p.preview_scale)
        self._vars["pause_hidden"].set(p.pause_hidden_panels)
        self._vars["reduce_minimized"].set(p.reduce_when_minimized)
        self._vars["adaptive"].set(p.adaptive_enabled)
        self._vars["jpeg_quality"].set(b.jpeg_quality)
        self._vars["buffer_seconds"].set(b.duration_seconds)
        self._vars["buffer_memory"].set(b.max_memory_mb)
        self._vars["queue_size"].set(b.encoder_queue_size)
        self._vars["store_nth"].set(b.store_every_nth_frame)
        self._vars["assist_width"].set(temp.takeoff_assist.downscale_width)

    def _build_camera(self, f: ttk.Frame) -> None:
        r = self._title(f, "Camera", "Kamera", "Camera changes require an application restart.", "Změny kamery vyžadují restart aplikace.")
        c = self.working.camera
        vals = {
            "source": tk.StringVar(value=c.source_type), "device": tk.IntVar(value=c.device_index),
            "width": tk.IntVar(value=c.width), "height": tk.IntVar(value=c.height), "fps": tk.DoubleVar(value=c.fps),
            "backend": tk.StringVar(value=c.backend), "fourcc": tk.StringVar(value=c.fourcc), "reconnect": tk.DoubleVar(value=c.reconnect_seconds),
        }
        camera_devices = enumerate_camera_devices(c.device_index)
        self._camera_choice_to_index = {device.label: device.index for device in camera_devices}
        selected_device = next((device.label for device in camera_devices if device.index == c.device_index), camera_devices[0].label)
        vals["camera_device_choice"] = tk.StringVar(value=selected_device)
        vals["camera_device_choice"].trace_add(
            "write",
            lambda *_: vals["device"].set(self._camera_choice_to_index.get(str(vals["camera_device_choice"].get()), c.device_index)),
        )
        self._vars.update(vals)
        self._row(f, r, "Source", "Zdroj", vals["source"], "combo", ("camera", "synthetic", "file"), impact="medium"); r += 1
        self.camera_device_combo = self._row(
            f, r, "Camera", "Kamera", vals["camera_device_choice"], "combo", tuple(self._camera_choice_to_index),
            desc_en="Available Windows camera names. The leading number is the OpenCV camera index; restart after changing it.",
            desc_cs="Dostupné názvy kamer ve Windows. Úvodní číslo je index kamery OpenCV; po změně aplikaci restartujte.",
            impact="low",
        ); r += 1
        self._row(f, r, "Width", "Šířka", vals["width"], impact="very_high"); r += 1
        self._row(f, r, "Height", "Výška", vals["height"], impact="very_high"); r += 1
        self._row(f, r, "Requested camera FPS", "Požadované FPS kamery", vals["fps"], desc_en="The camera may provide a lower actual rate. Check Diagnostics.", desc_cs="Kamera může poskytovat nižší skutečnou hodnotu. Ověř v Diagnostice.", impact="very_high"); r += 1
        self._row(f, r, "Windows backend", "Windows backend", vals["backend"], "combo", ("DSHOW", "MSMF", "ANY"), impact="medium"); r += 1
        self._row(f, r, "Camera FOURCC", "Formát FOURCC", vals["fourcc"], desc_en="MJPG often enables high FPS over USB.", desc_cs="MJPG často umožní vyšší FPS přes USB.", impact="high"); r += 1
        self._row(f, r, "Reconnect delay (seconds)", "Prodleva opětovného připojení", vals["reconnect"], impact="low")
        if self.on_camera_diagnostic:
            ttk.Button(f, text=self._txt("Run camera diagnostic", "Spustit diagnostiku kamery"), command=self.on_camera_diagnostic).grid(row=r + 1, column=0, sticky="w", pady=(12, 0))

    def _build_board(self, f: ttk.Frame) -> None:
        r = self._title(f, "Board calibration", "Kalibrace prkna", "The line can be moved and rotated. The ROI should cover only the take-off board and nearby shoe movement.", "Čáru lze posouvat a otáčet. ROI má pokrývat pouze odrazové prkno a blízký pohyb boty.")
        d = self.working.display
        values = {
            "guide_enabled": tk.BooleanVar(value=d.guide_enabled), "guide_x": tk.DoubleVar(value=d.guide_x_ratio),
            "guide_y": tk.DoubleVar(value=d.guide_y_ratio), "guide_angle": tk.DoubleVar(value=d.guide_angle_deg), "guide_width": tk.IntVar(value=d.guide_width_px),
            "roi_enabled": tk.BooleanVar(value=d.board_roi_enabled), "roi_visible": tk.BooleanVar(value=d.board_roi_visible),
            "roi_x": tk.DoubleVar(value=d.board_roi_x), "roi_y": tk.DoubleVar(value=d.board_roi_y),
            "roi_w": tk.DoubleVar(value=d.board_roi_width), "roi_h": tk.DoubleVar(value=d.board_roi_height),
        }
        self._vars.update(values)
        self._row(f, r, "Show digital take-off line", "Zobrazit digitální čáru", values["guide_enabled"], "check", impact="low"); r += 1
        self._row(f, r, "Line X position (0–1)", "Pozice čáry X (0–1)", values["guide_x"]); r += 1
        self._row(f, r, "Line Y position (0–1)", "Pozice čáry Y (0–1)", values["guide_y"]); r += 1
        self._row(f, r, "Line rotation (degrees)", "Natočení čáry (stupně)", values["guide_angle"]); r += 1
        self._row(f, r, "Line width", "Tloušťka čáry", values["guide_width"], impact="low"); r += 1
        self._row(f, r, "Enable board ROI", "Zapnout oblast prkna", values["roi_enabled"], "check", impact="low"); r += 1
        self._row(f, r, "Show ROI on main video", "Zobrazit ROI v hlavním videu", values["roi_visible"], "check", impact="low"); r += 1
        self._row(f, r, "ROI X", "ROI X", values["roi_x"]); r += 1
        self._row(f, r, "ROI Y", "ROI Y", values["roi_y"]); r += 1
        self._row(f, r, "ROI width", "Šířka ROI", values["roi_w"]); r += 1
        self._row(f, r, "ROI height", "Výška ROI", values["roi_h"])

    def _build_competition(self, f: ttk.Frame) -> None:
        r = self._title(f, "Competition", "Soutěž", "Turn competition management off for a clean judge-only replay screen.", "Vypnutím správy soutěže získáš čistou rozhodcovskou obrazovku bez kategorií a pořadníku.")
        c = self.working.competition
        vals = {
            "competition_enabled": tk.BooleanVar(value=c.enabled), "show_selector": tk.BooleanVar(value=c.show_competitor_selector),
            "show_board": tk.BooleanVar(value=c.show_competition_board), "show_banner": tk.BooleanVar(value=c.show_state_banner),
            "next_overlay": tk.BooleanVar(value=c.next_athlete_overlay), "operator_mode": tk.BooleanVar(value=c.operator_mode_enabled),
            "wizard_visible": tk.BooleanVar(value=c.wizard_button_visible), "keyboard_comp": tk.BooleanVar(value=c.keyboard_competition_controls),
        }
        self._vars.update(vals)
        self._row(f, r, "Enable competition management", "Zapnout správu soutěže", vals["competition_enabled"], "check", impact="low"); r += 1
        self._row(f, r, "Show current-athlete selector", "Zobrazit výběr závodníka", vals["show_selector"], "check", impact="low"); r += 1
        self._row(f, r, "Show competition board", "Zobrazit tabulku soutěže", vals["show_board"], "check", impact="medium"); r += 1
        self._row(f, r, "Show competition state banner", "Zobrazit stavový banner soutěže", vals["show_banner"], "check", desc_en="Off by default.", desc_cs="Ve výchozím stavu vypnuto.", impact="low"); r += 1
        self._row(f, r, "Show next-athlete overlay", "Zobrazit překryv dalšího závodníka", vals["next_overlay"], "check", impact="low"); r += 1
        self._row(f, r, "Enable operator/setup modes", "Zapnout režim operátora/nastavení", vals["operator_mode"], "check", impact="low"); r += 1
        self._row(f, r, "Show Competition Wizard button", "Zobrazit tlačítko průvodce soutěží", vals["wizard_visible"], "check"); r += 1
        self._row(f, r, "Enable keyboard competition controls", "Zapnout klávesové ovládání soutěže", vals["keyboard_comp"], "check")

    def _build_rounds(self, f: ttk.Frame) -> None:
        r = self._title(f, "Athletes & rounds", "Závodníci a kola", "Athletes rotate by round: everyone completes attempt 1 before attempt 2 begins.", "Závodníci se střídají po kolech: všichni dokončí první pokus, než začne druhý.")
        c = self.working.competition
        vals = {
            "boys_enabled": tk.BooleanVar(value=c.boys_enabled), "girls_enabled": tk.BooleanVar(value=c.girls_enabled),
            "boys_count": tk.IntVar(value=c.boys_competitors), "girls_count": tk.IntVar(value=c.girls_competitors),
            "default_tries": tk.IntVar(value=c.default_attempts_per_competitor),
        }
        self._vars.update(vals)
        self._row(f, r, "Enable Boys", "Zapnout chlapce", vals["boys_enabled"], "check"); r += 1
        self._row(f, r, "Number of Boys athletes", "Počet závodníků – chlapci", vals["boys_count"], desc_en="Athlete numbers are generated from 1 to this value.", desc_cs="Čísla závodníků se vytvoří od 1 do této hodnoty."); r += 1
        self._row(f, r, "Enable Girls", "Zapnout dívky", vals["girls_enabled"], "check"); r += 1
        self._row(f, r, "Number of Girls athletes", "Počet závodnic – dívky", vals["girls_count"]); r += 1
        self._row(f, r, "Qualification attempts per athlete", "Počet základních pokusů", vals["default_tries"], desc_en="Default is 3.", desc_cs="Výchozí hodnota je 3."); r += 1

        roster = self._section(f, r, "Per-athlete attempt overrides", "Individuální počet pokusů"); r += 1
        tree = ttk.Treeview(roster, columns=("group", "number", "tries"), show="headings", height=9, selectmode="browse")
        for col, label, width in (("group", self._txt("Group", "Skupina"), 110), ("number", self._txt("Athlete", "Závodník"), 90), ("tries", self._txt("Attempts", "Pokusy"), 90)):
            tree.heading(col, text=label); tree.column(col, width=width, anchor="center")
        tree.grid(row=0, column=0, columnspan=3, sticky="nsew")
        roster.rowconfigure(0, weight=1); roster.columnconfigure(0, weight=1)
        self.roster_tree = tree
        self.override_var = tk.IntVar(value=c.default_attempts_per_competitor)
        ttk.Spinbox(roster, textvariable=self.override_var, from_=1, to=20, width=8).grid(row=1, column=0, sticky="w", pady=(7, 0))
        ttk.Button(roster, text=self._txt("Set override", "Nastavit výjimku"), command=self._apply_roster_override).grid(row=1, column=1, sticky="w", padx=5, pady=(7, 0))
        ttk.Button(roster, text=self._txt("Use default", "Použít výchozí"), command=self._clear_roster_override).grid(row=1, column=2, sticky="w", pady=(7, 0))
        tree.bind("<<TreeviewSelect>>", self._roster_selected)
        self._refresh_roster_editor()

    def _refresh_roster_editor(self) -> None:
        if not self.roster_tree:
            return
        self.roster_tree.delete(*self.roster_tree.get_children())
        c = self.working.competition
        boys = int(self._vars.get("boys_count", tk.IntVar(value=c.boys_competitors)).get())
        girls = int(self._vars.get("girls_count", tk.IntVar(value=c.girls_competitors)).get())
        default = int(self._vars.get("default_tries", tk.IntVar(value=c.default_attempts_per_competitor)).get())
        for group, count in (("Boys", boys), ("Girls", girls)):
            for number in range(1, max(0, count) + 1):
                value = c.attempts_overrides.get(f"{group}:{number}", default)
                self.roster_tree.insert("", "end", iid=f"{group}:{number}", values=(group, number, value))

    def _roster_selected(self, _event=None) -> None:
        if self.roster_tree and self.roster_tree.selection():
            self.override_var.set(int(self.roster_tree.item(self.roster_tree.selection()[0], "values")[2]))

    def _apply_roster_override(self) -> None:
        if self.roster_tree and self.roster_tree.selection():
            key = self.roster_tree.selection()[0]
            self.working.competition.attempts_overrides[key] = int(self.override_var.get())
            self.roster_tree.set(key, "tries", self.override_var.get())
            self._mark_dirty()

    def _clear_roster_override(self) -> None:
        if self.roster_tree and self.roster_tree.selection():
            key = self.roster_tree.selection()[0]
            self.working.competition.attempts_overrides.pop(key, None)
            default = int(self._vars["default_tries"].get())
            self.roster_tree.set(key, "tries", default)
            self.override_var.set(default)
            self._mark_dirty()

    def _build_decisions(self, f: ttk.Frame) -> None:
        r = self._title(f, "Attempts & decisions", "Pokusy a rozhodnutí", "Recording completion and judging are independent. By default, returning to Live stores the result as Not decided and advances the roster.", "Dokončení záznamu a rozhodnutí jsou oddělené. Ve výchozím nastavení návrat na Živě uloží stav Nerozhodnuto a posune pořadník.")
        c = self.working.competition
        vals = {
            "decision_controls": tk.BooleanVar(value=c.decision_controls_enabled),
            "require_decision": tk.BooleanVar(value=c.require_decision_before_continue),
            "advance_complete": tk.BooleanVar(value=c.auto_advance_on_attempt_complete),
            "advance_decision": tk.BooleanVar(value=c.auto_advance_after_decision),
            "auto_evidence": tk.BooleanVar(value=c.auto_save_evidence),
            "auto_live": tk.BooleanVar(value=c.auto_return_live),
            "auto_live_delay": tk.DoubleVar(value=c.auto_return_delay_seconds),
            "special_results": tk.BooleanVar(value=c.enable_special_results),
            "athlete_timer_duration": tk.IntVar(value=self.working.athlete_timer.duration_seconds),
        }
        self._vars.update(vals)
        self._row(f, r, "Show decision buttons", "Zobrazit rozhodovací tlačítka", vals["decision_controls"], "check", impact="low"); r += 1
        self._row(f, r, "Require a decision before continuing", "Vyžadovat rozhodnutí před pokračováním", vals["require_decision"], "check", desc_en="Off by default. When off, Not decided attempts do not block the next athlete.", desc_cs="Ve výchozím stavu vypnuto. Nerozhodnutý pokus neblokuje dalšího závodníka."); r += 1
        self._row(f, r, "Advance athlete when attempt is completed", "Posunout závodníka po dokončení pokusu", vals["advance_complete"], "check"); r += 1
        self._row(f, r, "Advance immediately after a decision", "Posunout ihned po rozhodnutí", vals["advance_decision"], "check"); r += 1
        self._row(f, r, "Save evidence automatically after a decision", "Automaticky uložit důkaz po rozhodnutí", vals["auto_evidence"], "check", impact="medium"); r += 1
        self._row(f, r, "Return to Live automatically after a decision", "Automaticky se vrátit na Živě po rozhodnutí", vals["auto_live"], "check", impact="low"); r += 1
        self._row(f, r, "Automatic Live delay (seconds)", "Prodleva automatického návratu (s)", vals["auto_live_delay"]); r += 1
        self._row(f, r, "Enable Passed / DNS / Withdrawn / Reattempt", "Zapnout Vynecháno / DNS / Odstoupení / Opakování", vals["special_results"], "check")

        r += 1
        self._row(
            f, r,
            self.tr("settings.athlete_timer_duration"), self.tr("settings.athlete_timer_duration"),
            vals["athlete_timer_duration"], "spin",
            desc_en=self.tr("settings.athlete_timer_duration_help"),
            desc_cs=self.tr("settings.athlete_timer_duration_help"),
            impact="low", width=8,
        )

    def _build_final(self, f: ttk.Frame) -> None:
        r = self._title(f, "Final round", "Finále", "Because this camera tool does not measure distance, finalists are selected manually after qualification.", "Protože tento kamerový nástroj neměří délku, finalisté se po základní části vybírají ručně.")
        c = self.working.competition
        vals = {
            "final_enabled": tk.BooleanVar(value=c.final_round_enabled), "finalists_count": tk.IntVar(value=c.finalists_count),
            "final_attempts": tk.IntVar(value=c.final_attempts), "final_order": tk.StringVar(value=c.final_order),
            "boys_finalists": tk.StringVar(value=", ".join(str(v) for v in c.finalist_numbers_by_group.get("Boys", []))),
            "girls_finalists": tk.StringVar(value=", ".join(str(v) for v in c.finalist_numbers_by_group.get("Girls", []))),
        }
        self._vars.update(vals)
        self._row(f, r, "Enable final round", "Zapnout finálovou část", vals["final_enabled"], "check"); r += 1
        self._row(f, r, "Number advancing (8 / 10 / 12 / custom)", "Počet postupujících (8 / 10 / 12 / vlastní)", vals["finalists_count"]); r += 1
        self._row(f, r, "Additional attempts", "Další pokusy", vals["final_attempts"], desc_en="Default is 3.", desc_cs="Výchozí hodnota je 3."); r += 1
        self._row(f, r, "Final order", "Pořadí ve finále", vals["final_order"], "combo", ("same", "reverse", "manual")); r += 1
        self._row(f, r, "Boys finalists (comma separated)", "Finalisté – chlapci (oddělit čárkou)", vals["boys_finalists"], desc_en="Can also be selected when qualification finishes.", desc_cs="Lze vybrat také po dokončení základní části."); r += 1
        self._row(f, r, "Girls finalists (comma separated)", "Finalistky – dívky (oddělit čárkou)", vals["girls_finalists"])

    def _build_replay(self, f: ttk.Frame) -> None:
        r = self._title(f, "Replay & storage", "Replay a úložiště", "Temporary MP4 sessions preserve frozen attempts independently of the rolling live buffer.", "Dočasná MP4 uchovávají zmrazené pokusy nezávisle na průběžném živém bufferu.")
        b, a, e = self.working.buffer, self.working.attempts, self.working.export
        vals = {
            "buffer_seconds": tk.DoubleVar(value=b.duration_seconds), "buffer_memory": tk.IntVar(value=b.max_memory_mb),
            "pre": tk.DoubleVar(value=a.pre_seconds), "post": tk.DoubleVar(value=a.post_seconds),
            "retention": tk.DoubleVar(value=a.retention_minutes), "max_attempts": tk.IntVar(value=a.max_attempts),
            "cache_gb": tk.DoubleVar(value=a.max_cache_gb), "evidence_overlay": tk.BooleanVar(value=e.evidence_include_overlay),
            "evidence_raw": tk.BooleanVar(value=e.evidence_save_raw),
        }
        self._vars.update(vals)
        self._row(f, r, "Live buffer duration (seconds)", "Délka živého bufferu (s)", vals["buffer_seconds"], impact="very_high"); r += 1
        self._row(f, r, "Maximum live-buffer RAM (MB)", "Maximální RAM bufferu (MB)", vals["buffer_memory"], impact="high"); r += 1
        self._row(f, r, "Attempt pre-roll (seconds)", "Záznam před zmrazením (s)", vals["pre"], impact="high"); r += 1
        self._row(f, r, "Attempt post-roll (seconds)", "Záznam po zmrazení (s)", vals["post"], impact="medium"); r += 1
        self._row(f, r, "Temporary retention (minutes)", "Doba uchování (min)", vals["retention"], impact="medium"); r += 1
        self._row(f, r, "Maximum temporary recordings", "Maximální počet dočasných záznamů", vals["max_attempts"], impact="high"); r += 1
        self._row(f, r, "Maximum cache size (GB)", "Maximální velikost cache (GB)", vals["cache_gb"], impact="high"); r += 1
        self._row(f, r, "Save annotated evidence", "Ukládat anotovaný důkaz", vals["evidence_overlay"], "check", impact="low"); r += 1
        self._row(f, r, "Save untouched evidence PNG", "Ukládat původní důkazní PNG", vals["evidence_raw"], "check", impact="low")

    def _build_views(self, f: ttk.Frame) -> None:
        r = self._title(f, "Views", "Pohledy", "Hidden panels can stop rendering when Pause hidden panels is enabled.", "Skryté panely mohou přestat vykreslovat, pokud je zapnuta volba Pozastavit skryté panely.")
        d = self.working.display
        vals = {
            "layout": tk.StringVar(value=d.layout), "show_attempts": tk.BooleanVar(value=d.show_attempts_panel),
            "show_timeline": tk.BooleanVar(value=d.show_timeline), "show_status": tk.BooleanVar(value=d.show_status_bar),
            "show_live": tk.BooleanVar(value=d.show_live_preview), "show_decisions": tk.BooleanVar(value=d.show_decision_controls),
            "show_warnings": tk.BooleanVar(value=d.show_capture_warnings), "show_assist_badge": tk.BooleanVar(value=d.show_takeoff_assist_badge),
            "comparison_enabled": tk.BooleanVar(value=d.comparison_enabled), "comparison_offset": tk.IntVar(value=d.comparison_offset_frames),
            "attempts_width": tk.IntVar(value=d.attempts_panel_width), "timeline_height": tk.IntVar(value=d.timeline_height),
        }
        self._vars.update(vals)
        self._row(f, r, "Default video layout", "Výchozí rozložení videa", vals["layout"], "combo", ("replay_pip", "side_by_side", "board_detail", "comparison", "replay_only", "live_only"), impact="medium"); r += 1
        self._row(f, r, "Show recordings panel", "Zobrazit panel záznamů", vals["show_attempts"], "check", impact="low"); r += 1
        self._row(f, r, "Show timeline", "Zobrazit časovou osu", vals["show_timeline"], "check", impact="medium"); r += 1
        self._row(f, r, "Show status bar", "Zobrazit stavový řádek", vals["show_status"], "check", impact="low"); r += 1
        self._row(f, r, "Show live preview", "Zobrazit živý náhled", vals["show_live"], "check", impact="high"); r += 1
        self._row(f, r, "Show decision controls", "Zobrazit rozhodovací ovládání", vals["show_decisions"], "check", impact="low"); r += 1
        self._row(f, r, "Show capture warnings", "Zobrazit varování záznamu", vals["show_warnings"], "check", impact="low"); r += 1
        self._row(f, r, "Show Take-off Assist badge", "Zobrazit stav asistenta odrazu", vals["show_assist_badge"], "check", impact="low"); r += 1
        self._row(f, r, "Enable frame comparison view", "Zapnout porovnání snímků", vals["comparison_enabled"], "check", impact="high"); r += 1
        self._row(f, r, "Comparison frame offset", "Odstup porovnávaných snímků", vals["comparison_offset"], impact="medium"); r += 1
        self._row(f, r, "Recordings panel width", "Šířka panelu záznamů", vals["attempts_width"], impact="low"); r += 1
        self._row(f, r, "Timeline height", "Výška časové osy", vals["timeline_height"], impact="low")

    def _build_assist(self, f: ttk.Frame) -> None:
        r = self._title(f, "Take-off Assist", "Asistent odrazu", "Finds a local motion peak inside the board ROI. It never decides Valid or Foul.", "Vyhledá lokální vrchol pohybu uvnitř oblasti prkna. Nikdy sám nerozhodne platný pokus nebo přešlap.")
        a = self.working.takeoff_assist
        vals = {
            "assist_enabled": tk.BooleanVar(value=a.enabled), "assist_auto_seek": tk.BooleanVar(value=a.auto_seek_after_freeze),
            "quick_review": tk.BooleanVar(value=a.quick_review_enabled), "quick_speed": tk.DoubleVar(value=a.quick_review_speed),
            "assist_before": tk.DoubleVar(value=a.analysis_seconds_before_freeze), "assist_after": tk.DoubleVar(value=a.analysis_seconds_after_freeze),
            "assist_confidence": tk.DoubleVar(value=a.minimum_confidence), "assist_width": tk.IntVar(value=a.downscale_width),
        }
        self._vars.update(vals)
        self._row(f, r, "Enable Take-off Assist", "Zapnout asistenta odrazu", vals["assist_enabled"], "check", impact="high"); r += 1
        self._row(f, r, "Seek to candidate after Freeze", "Po zmrazení přesunout na kandidáta", vals["assist_auto_seek"], "check", impact="low"); r += 1
        self._row(f, r, "Enable Quick Review", "Zapnout rychlou kontrolu", vals["quick_review"], "check", impact="high"); r += 1
        self._row(f, r, "Quick Review speed", "Rychlost rychlé kontroly", vals["quick_speed"], impact="medium"); r += 1
        self._row(f, r, "Analyse seconds before Freeze", "Analyzovat sekundy před zmrazením", vals["assist_before"], impact="high"); r += 1
        self._row(f, r, "Analyse seconds after Freeze", "Analyzovat sekundy po zmrazení", vals["assist_after"], impact="medium"); r += 1
        self._row(f, r, "Minimum confidence (0–1)", "Minimální jistota (0–1)", vals["assist_confidence"], impact="low"); r += 1
        self._row(f, r, "Analysis width", "Šířka analýzy", vals["assist_width"], desc_en="Higher values cost more CPU. 160–240 is normally sufficient.", desc_cs="Vyšší hodnoty více zatěžují CPU. Obvykle stačí 160–240.", impact="very_high")

    def _build_hotkeys(self, f: ttk.Frame) -> None:
        r = self._title(f, "Hotkeys", "Klávesové zkratky", "Shortcuts are captured before focused buttons, so Space always controls Freeze/Live.", "Zkratky se zachytávají před aktivními tlačítky, takže mezerník vždy ovládá Zmrazit/Živě.")
        self._vars["hotkeys_enabled"] = tk.BooleanVar(value=self.working.hotkeys.enabled)
        self._row(f, r, "Enable application hotkeys", "Zapnout klávesové zkratky", self._vars["hotkeys_enabled"], "check", impact="low"); r += 1
        tree = ttk.Treeview(f, columns=("action", "key"), show="headings", height=14, selectmode="browse")
        tree.heading("action", text=self._txt("Action", "Akce")); tree.column("action", width=360)
        tree.heading("key", text=self._txt("Key", "Klávesa")); tree.column("key", width=160, anchor="center")
        tree.grid(row=r, column=0, columnspan=3, sticky="nsew"); f.rowconfigure(r, weight=1); r += 1
        for action in ACTION_LABELS:
            tree.insert("", "end", iid=action, values=(self._action_label(action), self.working.hotkeys.bindings.get(action, "")))
        self.hotkey_tree = tree
        bar = ttk.Frame(f, style="Panel.TFrame"); bar.grid(row=r, column=0, columnspan=3, sticky="w", pady=(7, 0))
        ttk.Button(bar, text=self._txt("Change…", "Změnit…"), command=self._change_hotkey).pack(side="left")
        ttk.Button(bar, text=self._txt("Clear", "Vymazat"), command=self._clear_hotkey).pack(side="left", padx=5)
        ttk.Button(bar, text=self._txt("Defaults", "Výchozí"), command=self._reset_hotkeys).pack(side="left")

    def _build_shuttle(self, f: ttk.Frame) -> None:
        r = self._title(f, "Contour ShuttleXpress", "Contour ShuttleXpress", "Jog steps frames; the spring-loaded outer ring selects recordings. Buttons are configurable.", "Jog posouvá po snímcích; vnější pružinový prstenec vybírá záznamy. Tlačítka jsou nastavitelná.")
        self._vars["shuttle_enabled"] = tk.BooleanVar(value=self.working.shuttle.enabled)
        self._vars["direct_hid"] = tk.BooleanVar(value=self.working.shuttle.direct_hid)
        self._row(f, r, "Enable ShuttleXpress", "Zapnout ShuttleXpress", self._vars["shuttle_enabled"], "check", impact="low"); r += 1
        self._row(f, r, "Use direct HID when available", "Použít přímé HID, pokud je dostupné", self._vars["direct_hid"], "check", impact="low"); r += 1
        inverse = {button: action for action, button in self.working.shuttle.button_map.items()}
        for button in range(1, 6):
            var = tk.StringVar(value=inverse.get(button, "none")); self.shuttle_vars[button] = var
            self._row(f, r, f"Button {button}", f"Tlačítko {button}", var, "combo", tuple(SHUTTLE_ACTIONS)); r += 1

    def _build_recovery(self, f: ttk.Frame) -> None:
        r = self._title(f, "Recovery & export", "Obnova a export", "These optional tools are useful for larger events but can remain disabled for a simple judge station.", "Tyto volitelné funkce jsou užitečné pro větší závody, ale na jednoduchém stanovišti mohou zůstat vypnuté.")
        c = self.working.competition
        vals = {
            "recovery_prompt": tk.BooleanVar(value=c.recovery_prompt_enabled), "event_export": tk.BooleanVar(value=c.event_export_enabled),
            "camera_diag": tk.BooleanVar(value=c.camera_diagnostic_enabled), "clear_new": tk.BooleanVar(value=c.clear_temp_on_new_competition),
        }
        self._vars.update(vals)
        self._row(f, r, "Offer recovery after a crash", "Nabídnout obnovu po pádu", vals["recovery_prompt"], "check", impact="low"); r += 1
        self._row(f, r, "Enable competition package export", "Zapnout export balíčku soutěže", vals["event_export"], "check", impact="medium"); r += 1
        self._row(f, r, "Enable Camera Diagnostic Wizard", "Zapnout průvodce diagnostikou kamery", vals["camera_diag"], "check", impact="medium"); r += 1
        self._row(f, r, "Clear temporary recordings when starting a new competition", "Při nové soutěži vymazat dočasné záznamy", vals["clear_new"], "check", impact="low")

    def _build_advanced(self, f: ttk.Frame) -> None:
        r = self._title(f, "Advanced", "Pokročilé", "Change these only when troubleshooting a specific camera or codec.", "Měň pouze při řešení konkrétního problému s kamerou nebo kodekem.")
        self._vars["temp_codec"] = tk.StringVar(value=self.working.attempts.temp_codec)
        self._vars["export_codec"] = tk.StringVar(value=self.working.export.codec)
        self._vars["queue_size"] = tk.IntVar(value=self.working.buffer.encoder_queue_size)
        self._vars["store_nth"] = tk.IntVar(value=self.working.buffer.store_every_nth_frame)
        self._row(f, r, "Temporary video codec", "Kodek dočasného videa", self._vars["temp_codec"], impact="high"); r += 1
        self._row(f, r, "Export video codec", "Kodek exportovaného videa", self._vars["export_codec"], impact="high"); r += 1
        self._row(f, r, "JPEG encoder queue size", "Velikost fronty JPEG enkodéru", self._vars["queue_size"], impact="medium"); r += 1
        self._row(f, r, "Store every Nth frame", "Ukládat každý N-tý snímek", self._vars["store_nth"], desc_en="Values above 1 reduce evidence temporal resolution.", desc_cs="Hodnoty nad 1 snižují časové rozlišení důkazu.", impact="very_high")

    def _change_hotkey(self) -> None:
        if not self.hotkey_tree or not self.hotkey_tree.selection():
            return
        action = self.hotkey_tree.selection()[0]
        prompt = tk.Toplevel(self); prompt.title(self._txt("Press a shortcut", "Stiskni zkratku")); prompt.geometry("380x140"); prompt.transient(self); prompt.grab_set()
        ttk.Label(prompt, text=self._txt(f"Press the new shortcut for\n{self._action_label(action)}", f"Stiskni novou zkratku pro\n{self._action_label(action)}"), justify="center").pack(expand=True)
        def captured(event):
            value = event_to_hotkey(event)
            if not value: return "break"
            for other, binding in self.working.hotkeys.bindings.items():
                if other != action and binding.lower() == value.lower():
                    messagebox.showerror(self._txt("Shortcut conflict", "Konflikt zkratek"), self._txt(f"{value} is already assigned to {self._action_label(other)}.", f"{value} je již přiřazeno akci {self._action_label(other)}."), parent=prompt)
                    return "break"
            self.working.hotkeys.bindings[action] = value
            self.hotkey_tree.set(action, "key", value)
            self._mark_dirty(); prompt.destroy(); return "break"
        prompt.bind("<KeyPress>", captured); prompt.focus_force()

    def _clear_hotkey(self) -> None:
        if self.hotkey_tree and self.hotkey_tree.selection():
            action = self.hotkey_tree.selection()[0]
            self.working.hotkeys.bindings[action] = ""
            self.hotkey_tree.set(action, "key", "")
            self._mark_dirty()

    def _reset_hotkeys(self) -> None:
        self.working.hotkeys.bindings = dict(DEFAULT_HOTKEYS)
        if self.hotkey_tree:
            for action in ACTION_LABELS:
                self.hotkey_tree.set(action, "key", self.working.hotkeys.bindings.get(action, ""))
        self._mark_dirty()

    @staticmethod
    def _parse_numbers(value: str) -> list[int]:
        result: list[int] = []
        for part in value.replace(";", ",").split(","):
            part = part.strip()
            if part:
                number = int(part)
                if number not in result:
                    result.append(number)
        return result

    def _apply_vars(self) -> AppConfig:
        w = self.working
        w.general.language = str(self._vars["language"].get())
        w.general.confirm_destructive_actions = bool(self._vars["confirm_destructive"].get())
        w.general.show_tooltips = bool(self._vars["show_tooltips"].get())
        d = w.display
        d.theme = str(self._vars["theme"].get()); d.fullscreen = bool(self._vars["fullscreen"].get()); d.remember_geometry = bool(self._vars["remember_geometry"].get())
        p = w.performance
        p.preset = str(self._vars["performance_preset"].get()); p.preview_refresh_hz = int(self._vars["preview_hz"].get())
        p.timeline_refresh_hz = int(self._vars["timeline_hz"].get()); p.status_refresh_hz = int(self._vars["status_hz"].get())
        p.attempts_refresh_hz = int(self._vars["attempts_hz"].get()); p.preview_scale = float(self._vars["preview_scale"].get())
        p.pause_hidden_panels = bool(self._vars["pause_hidden"].get()); p.reduce_when_minimized = bool(self._vars["reduce_minimized"].get())
        p.adaptive_enabled = bool(self._vars["adaptive"].get()); p.menu_throttle_enabled = bool(self._vars["menu_throttle"].get())
        d.refresh_hz = p.preview_refresh_hz
        b = w.buffer; b.jpeg_quality = int(self._vars["jpeg_quality"].get())
        cam = w.camera
        cam.source_type = str(self._vars["source"].get()); cam.device_index = int(self._vars["device"].get())
        cam.width = int(self._vars["width"].get()); cam.height = int(self._vars["height"].get()); cam.fps = float(self._vars["fps"].get())
        cam.backend = str(self._vars["backend"].get()); cam.fourcc = str(self._vars["fourcc"].get()); cam.reconnect_seconds = float(self._vars["reconnect"].get())
        d.guide_enabled = bool(self._vars["guide_enabled"].get()); d.guide_x_ratio = float(self._vars["guide_x"].get())
        d.guide_y_ratio = float(self._vars["guide_y"].get()); d.guide_angle_deg = float(self._vars["guide_angle"].get()); d.guide_width_px = int(self._vars["guide_width"].get())
        d.board_roi_enabled = bool(self._vars["roi_enabled"].get()); d.board_roi_visible = bool(self._vars["roi_visible"].get())
        d.board_roi_x = float(self._vars["roi_x"].get()); d.board_roi_y = float(self._vars["roi_y"].get()); d.board_roi_width = float(self._vars["roi_w"].get()); d.board_roi_height = float(self._vars["roi_h"].get())
        c = w.competition
        c.enabled = bool(self._vars["competition_enabled"].get()); c.show_competitor_selector = bool(self._vars["show_selector"].get()); c.show_competition_board = bool(self._vars["show_board"].get())
        c.show_state_banner = bool(self._vars["show_banner"].get()); c.next_athlete_overlay = bool(self._vars["next_overlay"].get()); c.operator_mode_enabled = bool(self._vars["operator_mode"].get())
        c.wizard_button_visible = bool(self._vars["wizard_visible"].get()); c.keyboard_competition_controls = bool(self._vars["keyboard_comp"].get())
        c.boys_enabled = bool(self._vars["boys_enabled"].get()); c.girls_enabled = bool(self._vars["girls_enabled"].get())
        c.boys_competitors = int(self._vars["boys_count"].get()); c.girls_competitors = int(self._vars["girls_count"].get()); c.default_attempts_per_competitor = int(self._vars["default_tries"].get())
        c.decision_controls_enabled = bool(self._vars["decision_controls"].get()); c.require_decision_before_continue = bool(self._vars["require_decision"].get())
        c.auto_advance_on_attempt_complete = bool(self._vars["advance_complete"].get()); c.auto_advance_after_decision = bool(self._vars["advance_decision"].get())
        c.auto_save_evidence = bool(self._vars["auto_evidence"].get()); c.auto_return_live = bool(self._vars["auto_live"].get()); c.auto_return_delay_seconds = float(self._vars["auto_live_delay"].get())
        c.enable_special_results = bool(self._vars["special_results"].get())
        w.athlete_timer.duration_seconds = int(self._vars["athlete_timer_duration"].get())
        c.final_round_enabled = bool(self._vars["final_enabled"].get()); c.finalists_count = int(self._vars["finalists_count"].get()); c.final_attempts = int(self._vars["final_attempts"].get()); c.final_order = str(self._vars["final_order"].get())
        c.finalist_numbers_by_group["Boys"] = self._parse_numbers(str(self._vars["boys_finalists"].get()))
        c.finalist_numbers_by_group["Girls"] = self._parse_numbers(str(self._vars["girls_finalists"].get()))
        c.recovery_prompt_enabled = bool(self._vars["recovery_prompt"].get()); c.event_export_enabled = bool(self._vars["event_export"].get()); c.camera_diagnostic_enabled = bool(self._vars["camera_diag"].get()); c.clear_temp_on_new_competition = bool(self._vars["clear_new"].get())
        a, e = w.attempts, w.export
        b.duration_seconds = float(self._vars["buffer_seconds"].get()); b.max_memory_mb = int(self._vars["buffer_memory"].get())
        a.pre_seconds = float(self._vars["pre"].get()); a.post_seconds = float(self._vars["post"].get()); a.retention_minutes = float(self._vars["retention"].get()); a.max_attempts = int(self._vars["max_attempts"].get()); a.max_cache_gb = float(self._vars["cache_gb"].get())
        e.evidence_include_overlay = bool(self._vars["evidence_overlay"].get()); e.evidence_save_raw = bool(self._vars["evidence_raw"].get())
        d.layout = str(self._vars["layout"].get()); d.show_attempts_panel = bool(self._vars["show_attempts"].get()); d.show_timeline = bool(self._vars["show_timeline"].get()); d.show_status_bar = bool(self._vars["show_status"].get())
        d.show_live_preview = bool(self._vars["show_live"].get()); d.show_decision_controls = bool(self._vars["show_decisions"].get()); d.show_capture_warnings = bool(self._vars["show_warnings"].get()); d.show_takeoff_assist_badge = bool(self._vars["show_assist_badge"].get())
        d.comparison_enabled = bool(self._vars["comparison_enabled"].get()); d.comparison_offset_frames = int(self._vars["comparison_offset"].get()); d.attempts_panel_width = int(self._vars["attempts_width"].get()); d.timeline_height = int(self._vars["timeline_height"].get())
        ta = w.takeoff_assist
        ta.enabled = bool(self._vars["assist_enabled"].get()); ta.auto_seek_after_freeze = bool(self._vars["assist_auto_seek"].get()); ta.quick_review_enabled = bool(self._vars["quick_review"].get()); ta.quick_review_speed = float(self._vars["quick_speed"].get())
        ta.analysis_seconds_before_freeze = float(self._vars["assist_before"].get()); ta.analysis_seconds_after_freeze = float(self._vars["assist_after"].get()); ta.minimum_confidence = float(self._vars["assist_confidence"].get()); ta.downscale_width = int(self._vars["assist_width"].get())
        w.hotkeys.enabled = bool(self._vars["hotkeys_enabled"].get()); w.shuttle.enabled = bool(self._vars["shuttle_enabled"].get()); w.shuttle.direct_hid = bool(self._vars["direct_hid"].get())
        w.shuttle.button_map = {action: button for button, var in self.shuttle_vars.items() if (action := var.get()) != "none"}
        a.temp_codec = str(self._vars["temp_codec"].get()); e.codec = str(self._vars["export_codec"].get()); b.encoder_queue_size = int(self._vars["queue_size"].get()); b.store_every_nth_frame = int(self._vars["store_nth"].get())
        w.validate()
        return w

    def _apply(self, close: bool) -> None:
        try:
            config = self._apply_vars()
            self.on_apply(deepcopy(config))
            self._dirty = False
            self.dirty_label.configure(text="")
            if close:
                self.destroy()
        except Exception as exc:
            messagebox.showerror(self._txt("Invalid settings", "Neplatné nastavení"), str(exc), parent=self)

    def _restore_defaults(self) -> None:
        if not messagebox.askyesno(self._txt("Restore defaults", "Obnovit výchozí"), self._txt("Apply all default settings now?", "Použít nyní všechna výchozí nastavení?"), parent=self):
            return
        defaults = AppConfig()
        defaults.general.language = self.working.general.language
        self.on_apply(defaults)
        self.destroy()

    def _cancel(self) -> None:
        if self._dirty:
            answer = messagebox.askyesnocancel(self._txt("Unsaved changes", "Neuložené změny"), self._txt("Apply changes before closing?", "Použít změny před zavřením?"), parent=self)
            if answer is None:
                return
            if answer:
                self._apply(True)
                return
        self.destroy()

    def _attach_dirty_traces(self) -> None:
        for var in self._vars.values():
            try: var.trace_add("write", lambda *_: self._mark_dirty())
            except (tk.TclError, AttributeError): pass

    def _mark_dirty(self) -> None:
        if self._initialising:
            return
        self._dirty = True
        self.dirty_label.configure(text=self.tr("settings.changed"))
