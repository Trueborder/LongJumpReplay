from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import ttk
from collections.abc import Callable

from .config import AppConfig, DEFAULT_HOTKEYS, PERFORMANCE_PRESETS, apply_low_resource_mode, apply_performance_preset
from .camera_devices import enumerate_camera_devices
from .hotkeys import event_to_hotkey
from .i18n import Translator
from .language_catalog import LANGUAGE_OPTIONS, language_from_option, language_option
from .theme import ask_themed_yes_no, ask_themed_yes_no_cancel, configure_popup, show_themed_info, style_popup_menu


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
        ("timer", "Athlete timer", "Časomíra závodníka"),
        ("final", "Final round", "Finále"),
        ("replay", "Replay & storage", "Replay a úložiště"),
        ("views", "Views", "Pohledy"),
        ("assist", "Take-off Assist", "Asistent odrazu"),
        ("hotkeys", "Hotkeys", "Klávesové zkratky"),
        ("shuttle", "ShuttleXpress", "ShuttleXpress"),
    ]
    CATEGORY_GROUPS = [
        ("essentials", "ESSENTIALS", "ZÁKLADNÍ", ("general", "appearance", "camera")),
        ("judging", "JUDGING WORKFLOW", "ROZHODOVÁNÍ", ("competition", "rounds", "decisions", "timer", "final")),
        ("replay", "REPLAY WORKSPACE", "PRACOVNÍ PLOCHA", ("board", "replay", "views", "assist")),
        ("system", "CONTROLS & SYSTEM", "OVLÁDÁNÍ A SYSTÉM", ("hotkeys", "shuttle", "performance")),
    ]

    def __init__(
        self,
        parent: tk.Misc,
        config: AppConfig,
        on_apply: Callable[[AppConfig], None],
        on_camera_diagnostic: Callable[[], None] | None = None,
        on_show_onboarding: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        configure_popup(self, parent)
        self.working = deepcopy(config)
        self.on_apply = on_apply
        self.on_camera_diagnostic = on_camera_diagnostic
        self.on_show_onboarding = on_show_onboarding
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
        self._page_canvases: dict[str, tk.Canvas] = {}
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
        self._description_headers: list[tuple[ttk.Frame, ttk.Label]] = []
        self._build()
        if "show_tooltips" in self._vars:
            self._vars["show_tooltips"].trace_add("write", lambda *_args: self._update_description_visibility())
            self._update_description_visibility()
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
        nav_wrapper = ttk.Frame(sidebar, style="Toolbar.TFrame")
        nav_wrapper.pack(fill="both", expand=True)
        nav_wrapper.rowconfigure(0, weight=1)
        nav_wrapper.columnconfigure(0, weight=1)
        nav_bg = ttk.Style(self).lookup("Toolbar.TFrame", "background") or self.cget("background")
        self.nav_canvas = tk.Canvas(nav_wrapper, highlightthickness=0, bd=0, background=nav_bg)
        self.nav_scrollbar = ttk.Scrollbar(nav_wrapper, orient="vertical", command=self.nav_canvas.yview)
        self.nav_canvas.configure(yscrollcommand=self.nav_scrollbar.set)
        self.nav_canvas.grid(row=0, column=0, sticky="nsew")
        self.nav_scrollbar.grid(row=0, column=1, sticky="ns", padx=(5, 0))
        self.nav_host = ttk.Frame(self.nav_canvas, style="Toolbar.TFrame")
        self._nav_window = self.nav_canvas.create_window((0, 0), window=self.nav_host, anchor="nw")
        self.nav_host.bind("<Configure>", self._update_navigation_scrollregion)
        self.nav_canvas.bind("<Configure>", self._resize_navigation_host)
        self._bind_navigation_wheel(self.nav_canvas)
        self._bind_navigation_wheel(self.nav_host)

        self.page_host = ttk.Frame(body, style="Panel.TFrame", padding=1)
        self.page_host.grid(row=0, column=1, sticky="nsew")
        definitions = {key: (en, cs) for key, en, cs in self.CATEGORY_DEFS}
        for group_key, group_en, group_cs, keys in self.CATEGORY_GROUPS:
            label = ttk.Label(self.nav_host, text=self._txt(group_en, group_cs), style="SettingsGroup.TLabel")
            label.pack(fill="x", padx=5, pady=(10 if self._nav_group_labels else 2, 4))
            self._bind_navigation_wheel(label)
            self._nav_group_labels[group_key] = label
            for key in keys:
                en, cs = definitions[key]
                self._category_group[key] = group_key
                button = ttk.Button(self.nav_host, text=self._txt(en, cs), style="SettingsNav.TButton", command=lambda k=key: self._show_page(k))
                button.pack(fill="x", pady=1)
                self._bind_navigation_wheel(button)
                self._nav_buttons[key] = button
        for key, _en, _cs in self.CATEGORY_DEFS:
            wrapper, inner = self._new_scroll_page()
            self._pages[key] = wrapper
            self._page_inners[key] = inner
            self._page_canvases[key] = self._pending_page_canvas

        self.search_var.trace_add("write", lambda *_: self._filter_navigation())
        self._build_general(self._page_inners["general"])
        self._build_appearance(self._page_inners["appearance"])
        self._build_performance(self._page_inners["performance"])
        self._build_camera(self._page_inners["camera"])
        self._build_board(self._page_inners["board"])
        self._build_competition(self._page_inners["competition"])
        self._build_rounds(self._page_inners["rounds"])
        self._build_decisions(self._page_inners["decisions"])
        self._build_timer(self._page_inners["timer"])
        self._build_final(self._page_inners["final"])
        self._build_replay(self._page_inners["replay"])
        self._build_views(self._page_inners["views"])
        self._build_assist(self._page_inners["assist"])
        self._build_hotkeys(self._page_inners["hotkeys"])
        self._build_shuttle(self._page_inners["shuttle"])
        for page_key, inner in self._page_inners.items():
            canvas = self._page_canvases.get(page_key)
            if canvas:
                self._bind_scroll_descendants(inner, canvas)

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
        self._bind_scroll_events(canvas, lambda direction, c=canvas: c.yview_scroll(direction, "units"))
        self._pending_page_canvas = canvas
        return wrapper, inner

    def _bind_scroll_descendants(self, widget: tk.Misc, canvas: tk.Canvas) -> None:
        self._bind_scroll_events(widget, lambda direction, c=canvas: c.yview_scroll(direction, "units"))
        for child in widget.winfo_children():
            self._bind_scroll_descendants(child, canvas)

    @staticmethod
    def _bind_scroll_events(widget: tk.Misc, scroll: Callable[[int], None]) -> None:
        def wheel(event: tk.Event) -> str:
            delta = getattr(event, "delta", 0)
            if delta:
                scroll(-1 if delta > 0 else 1)
            return "break"
        widget.bind("<MouseWheel>", wheel, add="+")
        widget.bind("<Button-4>", lambda _e: (scroll(-1), "break")[1], add="+")
        widget.bind("<Button-5>", lambda _e: (scroll(1), "break")[1], add="+")

    def _bind_navigation_wheel(self, widget: tk.Misc) -> None:
        self._bind_scroll_events(widget, lambda direction: self.nav_canvas.yview_scroll(direction, "units"))

    def _scroll_navigation(self, event: tk.Event) -> str:
        if event.delta:
            self.nav_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _update_navigation_scrollregion(self, _event: tk.Event | None = None) -> None:
        self.nav_canvas.configure(scrollregion=self.nav_canvas.bbox("all"))

    def _resize_navigation_host(self, event: tk.Event) -> None:
        self.nav_canvas.itemconfigure(self._nav_window, width=event.width)

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
        self.nav_canvas.yview_moveto(0.0)
        self.after_idle(self._update_navigation_scrollregion)

    def _title(self, frame: ttk.Frame, title_en: str, title_cs: str, desc_en: str = "", desc_cs: str = "") -> int:
        hero = ttk.Frame(frame, style="SettingsHero.TFrame", padding=(18, 15))
        hero.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        ttk.Label(hero, text=self._txt(title_en, title_cs), style="SettingsHeroTitle.TLabel").pack(anchor="w")
        if desc_en or desc_cs:
            hero_description = ttk.Label(
                hero,
                text=self._txt(desc_en, desc_cs),
                style="SettingsHeroDesc.TLabel",
                wraplength=640,
                justify="left",
            )
            hero_description.pack(fill="x", anchor="w", pady=(5, 0))
            self._bind_responsive_wrap(hero_description, minimum=260, maximum=760)
        columns = ttk.Frame(frame, style="SettingsGroup.TFrame", padding=(14, 5))
        columns.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 2))
        self._configure_row_columns(columns)
        ttk.Label(columns, text=self.tr("settings.column.option"), style="SettingsGroup.TLabel").grid(row=0, column=0, sticky="w")
        description_header = ttk.Label(columns, text=self.tr("settings.column.description"), style="SettingsGroup.TLabel")
        description_header.grid(row=0, column=1, sticky="w", padx=(18, 18))
        self._description_headers.append((columns, description_header))
        ttk.Label(columns, text=self.tr("settings.column.value"), style="SettingsGroup.TLabel").grid(row=0, column=2, sticky="w")
        frame.columnconfigure(0, weight=1)
        return 2

    @staticmethod
    def _configure_row_columns(container: ttk.Frame) -> None:
        container.columnconfigure(0, minsize=220, weight=0)
        container.columnconfigure(1, minsize=300, weight=1)
        container.columnconfigure(2, minsize=160, weight=0)

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
            # Keep long option lists from making the Value column wider than the page.
            combo_width = max(12, min(16, int(width))) if width is not None else 14
            widget = ttk.Combobox(card, textvariable=var, values=values, state="readonly", width=combo_width)
        elif kind == "spin":
            value_width = width if width is not None else 10
            widget = ttk.Spinbox(card, textvariable=var, from_=0, to=10000, increment=1, width=value_width)
        else:
            value_width = width if width is not None else 14
            widget = ttk.Entry(card, textvariable=var, width=value_width)
        if not (desc_en or desc_cs):
            desc_en = f"Adjusts {label_en.lower()}."
            desc_cs = f"Upravuje volbu „{label_cs}“."
        description = ttk.Label(
            card,
            text=self._txt(desc_en, desc_cs),
            style="SettingsRowDesc.TLabel",
            wraplength=260,
            justify="left",
        )
        description.grid(row=0, column=1, sticky="new", padx=(18, 18))
        self._bind_responsive_wrap(description, minimum=180, maximum=520)
        widget.grid(row=0, column=2, sticky="w" if kind == "check" else "ew")
        self._setting_rows.append((card, widget, description))
        return widget

    @staticmethod
    def _bind_responsive_wrap(label: ttk.Label, minimum: int = 180, maximum: int = 760) -> None:
        """Keep explanatory text inside the space assigned by the current page width."""
        def resize(event: tk.Event) -> None:
            width = max(minimum, min(maximum, int(getattr(event, "width", 0))))
            if int(label.cget("wraplength") or 0) != width:
                label.configure(wraplength=width)

        label.bind("<Configure>", resize, add="+")

    def _update_description_visibility(self) -> None:
        visible = bool(self._vars.get("show_tooltips") and self._vars["show_tooltips"].get())
        for card, _widget, description in self._setting_rows:
            card.columnconfigure(1, minsize=300 if visible else 0, weight=1 if visible else 0)
            if description is not None:
                description.grid() if visible else description.grid_remove()
        for columns, header in self._description_headers:
            columns.columnconfigure(1, minsize=300 if visible else 0, weight=1 if visible else 0)
            header.grid() if visible else header.grid_remove()

    def _section(self, frame: ttk.Frame, row: int, title_en: str, title_cs: str) -> ttk.LabelFrame:
        box = ttk.LabelFrame(frame, text=self._txt(title_en, title_cs), padding=10, style="SettingsSection.TLabelframe")
        box.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(10, 4))
        for column in range(5):
            box.columnconfigure(column, weight=1)
        return box

    def _build_general(self, f: ttk.Frame) -> None:
        r = self._title(f, "General", "Obecné", "Basic application behaviour.", "Základní chování aplikace.")
        g = self.working.general
        self._vars["confirm_destructive"] = tk.BooleanVar(value=g.confirm_destructive_actions)
        self._vars["show_tooltips"] = tk.BooleanVar(value=g.show_tooltips)
        self._vars["fullscreen"] = tk.BooleanVar(value=self.working.display.fullscreen)
        self._vars["remember_geometry"] = tk.BooleanVar(value=self.working.display.remember_geometry)
        self._row(f, r, "Confirm destructive actions", "Potvrzovat mazání", self._vars["confirm_destructive"], "check", desc_en="Shows a confirmation before clearing or deleting recordings.", desc_cs="Před smazáním záznamů zobrazí potvrzení."); r += 1
        self._row(
            f, r, "Show setting descriptions", "Zobrazovat popisy nastavení", self._vars["show_tooltips"], "check",
            desc_en="Shows or hides the middle Description column immediately throughout Settings.",
            desc_cs="Okamžitě zobrazí nebo skryje prostřední sloupec Popis v celém Nastavení.",
        ); r += 1
        self._row(f, r, "Start fullscreen", "Spustit přes celou obrazovku", self._vars["fullscreen"], "check", impact="low"); r += 1
        self._row(f, r, "Remember window and panel sizes", "Pamatovat velikost okna a panelů", self._vars["remember_geometry"], "check")

        glossary = self._section(f, r + 1, "Plain-language glossary", "Slovníček jednoduchými slovy")
        glossary.columnconfigure(0, weight=1)
        glossary.columnconfigure(1, weight=1)
        glossary_terms = (
            (
                "Buffer",
                "Paměť bufferu",
                "Short rolling memory of recent camera frames.",
                "Krátká paměť posledních snímků z kamery.",
            ),
            (
                "ROI",
                "ROI",
                "The selected area where take-off motion is analysed.",
                "Vybraná oblast, kde se analyzuje pohyb při odrazu.",
            ),
            (
                "FPS",
                "FPS",
                "Frames per second: how many images are shown or recorded each second.",
                "Snímky za sekundu: kolik obrázků se zobrazí nebo uloží za sekundu.",
            ),
            (
                "Codec",
                "Kodek",
                "The format used to store and compress video.",
                "Formát používaný pro uložení a kompresi videa.",
            ),
            (
                "HID",
                "HID",
                "Direct communication with a USB controller such as ShuttleXpress.",
                "Přímá komunikace s USB ovladačem, například ShuttleXpress.",
            ),
            (
                "JPEG quality",
                "Kvalita JPEG",
                "How strongly the live preview is compressed. Higher values look clearer and use more space.",
                "Míra komprese živého náhledu. Vyšší hodnota znamená lepší obraz a větší nároky na místo.",
            ),
        )
        for index, (term_en, term_cs, definition_en, definition_cs) in enumerate(glossary_terms):
            column = index % 2
            item = ttk.Frame(glossary, style="SettingsRow.TFrame", padding=(10, 8))
            item.grid(
                row=index // 2,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 6, 6 if column == 0 else 0),
                pady=3,
            )
            item.columnconfigure(0, weight=1)
            ttk.Label(
                item,
                text=self._txt(term_en, term_cs),
                style="SettingsRowTitle.TLabel",
            ).grid(row=0, column=0, sticky="w")
            definition = ttk.Label(
                item,
                text=self._txt(definition_en, definition_cs),
                style="SettingsRowDesc.TLabel",
                wraplength=280,
                justify="left",
            )
            definition.grid(row=1, column=0, sticky="ew", pady=(3, 0))
            self._bind_responsive_wrap(definition, minimum=150, maximum=420)
        if self.on_show_onboarding:
            ttk.Button(f, text=self._txt("Show the tutorial again", "Znovu zobrazit výukový program"), command=self.on_show_onboarding).grid(row=r + 2, column=0, sticky="w", pady=(10, 0))

    def _build_appearance(self, f: ttk.Frame) -> None:
        r = self._title(f, "Language & appearance", "Jazyk a vzhled", "The language is applied to the main interface after Apply.", "Jazyk se na hlavní rozhraní použije po stisku Použít.")
        self._vars["language"] = tk.StringVar(value=language_option(self.working.general.language))
        self._vars["theme"] = tk.StringVar(value=self.working.display.theme)
        self._row(f, r, "Language", "Jazyk", self._vars["language"], "combo", LANGUAGE_OPTIONS, desc_en="Choose a language by its native name. Specialist text falls back to English when needed.", desc_cs="Vyberte jazyk podle jeho vlastního názvu. Specializovaný text se v případě potřeby zobrazí anglicky."); r += 1
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
            # Retained as non-visible compatibility state for the explicit
            # low-resource preset; the customer does not edit these directly.
            "queue_size": tk.IntVar(value=self.working.buffer.encoder_queue_size),
            "store_nth": tk.IntVar(value=self.working.buffer.store_every_nth_frame),
        })
        preset_box = self._section(f, r, "Performance preset", "Výkonový profil"); r += 1
        performance_intro = ttk.Label(
            preset_box,
            text=self._txt("Choose a profile to fill the controls below. Apply saves the profile and its values; camera FPS, stored evidence, and export quality stay unchanged.", "Vyber profil, který vyplní níže uvedené volby. Použít uloží profil a jeho hodnoty; FPS kamery, uložený důkaz a kvalita exportu se nemění."),
            style="SettingsRowDesc.TLabel", wraplength=640, justify="left",
        )
        performance_intro.grid(row=0, column=0, columnspan=5, sticky="ew", pady=(0, 9))
        self._bind_responsive_wrap(performance_intro, minimum=220, maximum=760)
        preset_names = {
            "quiet": self._txt("Quiet", "Tichý"),
            "balanced": self._txt("Balanced", "Vyvážený"),
            "high": self._txt("High", "Výkonný"),
            "evidence": self._txt("Evidence focus", "Důkazní detail"),
            "custom": self._txt("Custom", "Vlastní"),
        }
        for column, value in enumerate(preset_names):
            preset_box.columnconfigure(column, weight=1)
            ttk.Button(
                preset_box, text=preset_names[value], style="MutedAction.TButton",
                command=lambda value=value: self._choose_performance_preset(value),
            ).grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else 5, 0))
        self.preset_description = ttk.Label(preset_box, style="Muted.TLabel", wraplength=650, justify="left")
        self.preset_description.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(9, 0))
        self._bind_responsive_wrap(self.preset_description, minimum=220, maximum=760)
        performance_warning = ttk.Label(
            preset_box,
            text=self._txt(
                "Older PC mode explicitly retains every second camera frame and needs an app restart.",
                "Režim pro slabší PC výslovně ukládá každý druhý snímek kamery a vyžaduje restart aplikace.",
            ),
            style="Warning.TLabel",
            wraplength=560,
            justify="left",
        )
        performance_warning.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        self._bind_responsive_wrap(performance_warning, minimum=220, maximum=760)
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
        self._row(f, r, "Live buffer JPEG quality", "Kvalita JPEG v živém bufferu", self._vars["jpeg_quality"], desc_en="This is only the compressed rolling preview copy. Higher values use more CPU and RAM; evidence PNG remains lossless.", desc_cs="Jde pouze o komprimovanou kopii průběžného náhledu. Vyšší hodnoty využijí více CPU a RAM; důkazní PNG zůstává bezeztrátové.", impact="very_high")

    def _choose_performance_preset(self, preset: str) -> None:
        self._vars["performance_preset"].set(preset)
        self._load_performance_preset()

    def _update_preset_description(self) -> None:
        if not hasattr(self, "preset_description"):
            return
        preset = self._vars.get("performance_preset", tk.StringVar(value="balanced")).get()
        descriptions = {
            "quiet": self._txt("Lowest fan noise and CPU use. Best for webcams and older laptops.", "Nejnižší hluk ventilátoru a využití CPU. Vhodné pro webkamery a slabší notebooky."),
            "balanced": self._txt("Recommended default. Smooth controls without wasting CPU on invisible detail.", "Doporučené výchozí nastavení. Plynulé ovládání bez zbytečné spotřeby CPU."),
            "high": self._txt("Faster preview and seeking for powerful computers. Higher fan noise.", "Rychlejší náhled a posun pro výkonné počítače. Vyšší hluk ventilátoru."),
            "evidence": self._txt("Prioritises a full-resolution preview and higher-detail board analysis. Higher CPU use; buffer quality remains explicit.", "Upřednostňuje náhled v plném rozlišení a podrobnější analýzu prkna. Vyšší využití CPU; kvalita bufferu zůstává samostatnou volbou."),
            "custom": self._txt("Manual values are active. Presets change display workload only; they do not alter camera capture or evidence quality.", "Jsou aktivní ruční hodnoty. Profily mění pouze zátěž zobrazení; nemění záznam kamery ani kvalitu důkazu."),
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
        self._vars["menu_throttle"].set(p.menu_throttle_enabled)
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
            "source": tk.StringVar(value=c.source_type if c.source_type in {"camera", "file"} else "camera"), "device": tk.IntVar(value=c.device_index),
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
        self._row(f, r, "Source", "Zdroj", vals["source"], "combo", ("camera", "file"), impact="medium"); r += 1
        self.camera_device_combo = self._row(
            f, r, "Camera", "Kamera", vals["camera_device_choice"], "combo", tuple(self._camera_choice_to_index),
            desc_en="Available Windows camera names. The leading number is the OpenCV camera index; restart after changing it.",
            desc_cs="Dostupné názvy kamer ve Windows. Úvodní číslo je index kamery OpenCV; po změně aplikaci restartujte.",
            impact="low",
        ); r += 1
        self._row(f, r, "Width", "Šířka", vals["width"], impact="very_high"); r += 1
        self._row(f, r, "Height", "Výška", vals["height"], impact="very_high"); r += 1
        self._row(f, r, "Requested camera FPS", "Požadované FPS kamery", vals["fps"], desc_en="The camera may provide a lower actual rate; the current status is shown after startup.", desc_cs="Kamera může poskytovat nižší skutečnou hodnotu; aktuální stav se zobrazí po spuštění.", impact="very_high"); r += 1
        self._row(f, r, "Windows backend", "Windows backend", vals["backend"], "combo", ("DSHOW", "MSMF", "ANY"), impact="medium"); r += 1
        self._row(f, r, "Camera FOURCC", "Formát FOURCC", vals["fourcc"], desc_en="MJPG often enables high FPS over USB.", desc_cs="MJPG často umožní vyšší FPS přes USB.", impact="high"); r += 1
        self._row(f, r, "Reconnect delay (seconds)", "Prodleva opětovného připojení", vals["reconnect"], impact="low")
    def _build_board(self, f: ttk.Frame) -> None:
        r = self._title(f, "Board calibration", "Kalibrace prkna", "Calibrate the line and ROI directly on the main video. Numeric position fields are intentionally not duplicated here.", "Kalibraci čáry a ROI prováděj přímo v hlavním videu. Číselná pole pro polohu zde záměrně neopakujeme.")
        d = self.working.display
        values = {
            "guide_enabled": tk.BooleanVar(value=d.guide_enabled), "guide_width": tk.IntVar(value=d.guide_width_px),
            "roi_enabled": tk.BooleanVar(value=d.board_roi_enabled), "roi_visible": tk.BooleanVar(value=d.board_roi_visible),
        }
        self._vars.update(values)
        self._row(f, r, "Show digital take-off line", "Zobrazit digitální čáru", values["guide_enabled"], "check", impact="low"); r += 1
        self._row(f, r, "Line width", "Tloušťka čáry", values["guide_width"], impact="low"); r += 1
        self._row(f, r, "Enable board ROI", "Zapnout oblast prkna", values["roi_enabled"], "check", impact="low"); r += 1
        self._row(f, r, "Show ROI on main video", "Zobrazit ROI v hlavním videu", values["roi_visible"], "check", impact="low"); r += 1
        guide_box = self._section(f, r + 1, "Calibrate on the main video", "Kalibruj v hlavním videu")
        calibration_help = ttk.Label(
            guide_box,
            text=self._txt(
                "Open View → Board calibration. Drag the red line centre to move it, drag the yellow handle to rotate it, and Shift-drag to draw or resize the ROI. Ctrl + mouse wheel fine-rotates the line. The calibrated values are saved automatically when calibration mode closes.",
                "Otevři Zobrazení → Kalibrace prkna. Tažením středu červené čáry ji posuň, žlutým úchytem ji otoč a tažením se Shiftem nakresli nebo uprav ROI. Ctrl + kolečko čáru jemně otočí. Hodnoty se automaticky uloží po zavření kalibrace.",
            ),
            style="SettingsRowDesc.TLabel", wraplength=640, justify="left",
        )
        calibration_help.grid(row=0, column=0, columnspan=5, sticky="ew")
        self._bind_responsive_wrap(calibration_help, minimum=220, maximum=760)

    def _build_competition(self, f: ttk.Frame) -> None:
        r = self._title(f, "Competition", "Soutěž", "Turn competition management off for a clean judge-only replay screen.", "Vypnutím správy soutěže získáš čistou rozhodcovskou obrazovku bez kategorií a pořadníku.")
        c = self.working.competition
        vals = {
            "competition_enabled": tk.BooleanVar(value=c.enabled), "show_selector": tk.BooleanVar(value=c.show_competitor_selector),
            "show_board": tk.BooleanVar(value=c.show_competition_board), "show_banner": tk.BooleanVar(value=c.show_state_banner),
            "next_overlay": tk.BooleanVar(value=c.next_athlete_overlay),
            "wizard_visible": tk.BooleanVar(value=c.wizard_button_visible), "keyboard_comp": tk.BooleanVar(value=c.keyboard_competition_controls),
        }
        self._vars.update(vals)
        self._row(f, r, "Enable competition management", "Zapnout správu soutěže", vals["competition_enabled"], "check", impact="low"); r += 1
        self._row(
            f, r, "Show next-attempt panel on board", "Zobrazit panel dalšího pokusu na tabuli",
            vals["show_selector"], "check",
            desc_en="Shows the next athlete number and attempt directly above the Competition Board.",
            desc_cs="Zobrazí číslo dalšího závodníka a pokusu přímo nad soutěžní tabulí.", impact="low",
        ); r += 1
        self._row(f, r, "Show competition board", "Zobrazit tabulku soutěže", vals["show_board"], "check", impact="medium"); r += 1
        self._row(f, r, "Show competition state banner", "Zobrazit stavový banner soutěže", vals["show_banner"], "check", desc_en="Off by default.", desc_cs="Ve výchozím stavu vypnuto.", impact="low"); r += 1
        self._row(f, r, "Show next-athlete overlay", "Zobrazit překryv dalšího závodníka", vals["next_overlay"], "check", impact="low"); r += 1
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


    def _build_timer(self, f: ttk.Frame) -> None:
        r = self._title(
            f, "Athlete timer", "Časomíra závodníka",
            "Operator-started countdown for the current attempt. It does not affect judging, recordings, or exports.",
            "Odpočet spouštěný obsluhou pro aktuální pokus. Neovlivňuje rozhodnutí, záznamy ani exporty.",
        )
        value = tk.IntVar(value=self.working.athlete_timer.duration_seconds)
        self._vars["athlete_timer_duration"] = value
        self._row(
            f, r, self.tr("settings.athlete_timer_duration"), self.tr("settings.athlete_timer_duration"), value, "spin",
            desc_en=self.tr("settings.athlete_timer_duration_help"),
            desc_cs=self.tr("settings.athlete_timer_duration_help"), impact="low", width=8,
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
        bar = ttk.Frame(f, style="Panel.TFrame"); bar.grid(row=r, column=0, columnspan=3, sticky="ew", pady=(2, 7))
        ttk.Button(bar, text=self._txt("Defaults", "Výchozí"), style="MutedAction.TButton", command=self._reset_hotkeys).pack(side="left")
        ttk.Label(bar, text=self._txt("Double-click a row to change its shortcut. Right-click restores one row.", "Dvojklikem na řádek zkratku změníš. Pravé tlačítko obnoví jednu zkratku."), style="SettingsRowDesc.TLabel").pack(side="left", padx=(12, 0))
        r += 1
        tree = ttk.Treeview(f, columns=("action", "key"), show="headings", height=14, selectmode="browse")
        tree.heading("action", text=self._txt("Action", "Akce")); tree.column("action", width=360)
        tree.heading("key", text=self._txt("Key", "Klávesa")); tree.column("key", width=160, anchor="center")
        tree.grid(row=r, column=0, columnspan=3, sticky="nsew"); f.rowconfigure(r, weight=1); r += 1
        for action in ACTION_LABELS:
            tree.insert("", "end", iid=action, values=(self._action_label(action), self.working.hotkeys.bindings.get(action, "")))
        self.hotkey_tree = tree
        tree.bind("<Double-1>", lambda _event: self._change_hotkey())
        tree.bind("<Button-3>", self._hotkey_context_menu)

    def _hotkey_context_menu(self, event: tk.Event) -> str:
        if not self.hotkey_tree:
            return "break"
        row = self.hotkey_tree.identify_row(event.y)
        if not row:
            return "break"
        self.hotkey_tree.selection_set(row)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label=self._txt("Restore default", "Obnovit výchozí"), command=self._restore_selected_hotkey)
        style_popup_menu(menu, self)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

    def _restore_selected_hotkey(self) -> None:
        if self.hotkey_tree and self.hotkey_tree.selection():
            action = self.hotkey_tree.selection()[0]
            self.working.hotkeys.bindings[action] = DEFAULT_HOTKEYS.get(action, "")
            self.hotkey_tree.set(action, "key", self.working.hotkeys.bindings[action])
            self._mark_dirty()

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
        prompt = tk.Toplevel(self); configure_popup(prompt, self); prompt.title(self._txt("Press a shortcut", "Stiskni zkratku")); prompt.geometry("380x140"); prompt.transient(self); prompt.grab_set()
        ttk.Label(prompt, text=self._txt(f"Press the new shortcut for\n{self._action_label(action)}", f"Stiskni novou zkratku pro\n{self._action_label(action)}"), justify="center").pack(expand=True)
        def captured(event):
            value = event_to_hotkey(event)
            if not value: return "break"
            for other, binding in self.working.hotkeys.bindings.items():
                if other != action and binding.lower() == value.lower():
                    show_themed_info(prompt, self._txt("Shortcut conflict", "Konflikt zkratek"), self._txt(f"{value} is already assigned to {self._action_label(other)}.", f"{value} je již přiřazeno akci {self._action_label(other)}."))
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
        w.general.language = language_from_option(str(self._vars["language"].get()))
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
        d.guide_enabled = bool(self._vars["guide_enabled"].get()); d.guide_width_px = int(self._vars["guide_width"].get())
        d.board_roi_enabled = bool(self._vars["roi_enabled"].get()); d.board_roi_visible = bool(self._vars["roi_visible"].get())
        c = w.competition
        c.enabled = bool(self._vars["competition_enabled"].get()); c.show_competitor_selector = bool(self._vars["show_selector"].get()); c.show_competition_board = bool(self._vars["show_board"].get())
        c.show_state_banner = bool(self._vars["show_banner"].get()); c.next_athlete_overlay = bool(self._vars["next_overlay"].get()); c.operator_mode_enabled = False
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
        b.encoder_queue_size = int(self._vars["queue_size"].get()); b.store_every_nth_frame = int(self._vars["store_nth"].get())
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
            show_themed_info(self, self._txt("Invalid settings", "Neplatné nastavení"), str(exc))

    def _restore_defaults(self) -> None:
        if not ask_themed_yes_no(self, self._txt("Restore defaults", "Obnovit výchozí"), self._txt("Apply all default settings now?", "Použít nyní všechna výchozí nastavení?"), yes=self._txt("Restore", "Obnovit"), no=self._txt("Cancel", "Zrušit")):
            return
        defaults = AppConfig()
        defaults.general.language = self.working.general.language
        self.on_apply(defaults)
        self.destroy()

    def _cancel(self) -> None:
        if self._dirty:
            answer = ask_themed_yes_no_cancel(self, self._txt("Unsaved changes", "Neuložené změny"), self._txt("Apply changes before closing?", "Použít změny před zavřením?"), yes=self._txt("Apply", "Použít"), no=self._txt("Discard", "Zahodit"), cancel=self._txt("Cancel", "Zrušit"))
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
