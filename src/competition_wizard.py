from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import messagebox, ttk
from collections.abc import Callable

from .config import AppConfig, apply_performance_preset
from .i18n import Translator


class CompetitionWizard(tk.Toplevel):
    """Guided per-event setup. Advanced options remain in Settings."""

    def __init__(self, parent: tk.Misc, config: AppConfig, on_finish: Callable[[AppConfig, bool], None]) -> None:
        super().__init__(parent)
        self.working = deepcopy(config)
        self.on_finish = on_finish
        self.tr = Translator(config.general.language)
        self.lang = config.general.language
        self.title(self.tr("wizard.title"))
        self.geometry("820x640")
        self.minsize(720, 560)
        self.transient(parent)
        self.grab_set()
        self.index = 0
        self.pages: list[ttk.Frame] = []
        self.vars: dict[str, tk.Variable] = {}
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._show(0)

    def _txt(self, en: str, cs: str) -> str:
        return cs if self.lang == "cs" else en

    def _build(self) -> None:
        shell = ttk.Frame(self, style="App.TFrame", padding=14)
        shell.pack(fill="both", expand=True)
        self.title_var = tk.StringVar()
        ttk.Label(shell, textvariable=self.title_var, style="Title.TLabel").pack(anchor="w")
        self.step_var = tk.StringVar()
        ttk.Label(shell, textvariable=self.step_var, style="HeaderMuted.TLabel").pack(anchor="w", pady=(2, 10))
        self.host = ttk.Frame(shell, style="Panel.TFrame", padding=16)
        self.host.pack(fill="both", expand=True)
        for builder in (self._mode_page, self._athletes_page, self._attempts_page, self._camera_page, self._storage_page, self._review_page):
            frame = ttk.Frame(self.host, style="Panel.TFrame")
            self.pages.append(frame)
            builder(frame)
        footer = ttk.Frame(shell, style="Toolbar.TFrame", padding=(8, 7))
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text=self.tr("wizard.cancel"), command=self.destroy).pack(side="left")
        self.back_button = ttk.Button(footer, text=self.tr("wizard.back"), command=lambda: self._show(self.index - 1))
        self.back_button.pack(side="right", padx=(6, 0))
        self.next_button = ttk.Button(footer, text=self.tr("wizard.next"), style="Accent.TButton", command=self._next)
        self.next_button.pack(side="right")

    def _section_title(self, frame, en: str, cs: str, desc_en: str = "", desc_cs: str = "") -> int:
        ttk.Label(frame, text=self._txt(en, cs), style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        if desc_en:
            ttk.Label(frame, text=self._txt(desc_en, desc_cs), style="Muted.TLabel", wraplength=650, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 14))
        frame.columnconfigure(1, weight=1)
        return 2

    def _row(self, frame, row: int, en: str, cs: str, var: tk.Variable, kind="entry", values=(), desc_en="", desc_cs=""):
        ttk.Label(frame, text=self._txt(en, cs), style="Text.TLabel").grid(row=row, column=0, sticky="w", pady=7, padx=(0, 14))
        if kind == "check": widget = ttk.Checkbutton(frame, variable=var)
        elif kind == "combo": widget = ttk.Combobox(frame, textvariable=var, values=values, state="readonly")
        else: widget = ttk.Entry(frame, textvariable=var)
        widget.grid(row=row, column=1, sticky="ew", pady=7)
        if desc_en:
            ttk.Label(frame, text=self._txt(desc_en, desc_cs), style="Muted.TLabel", wraplength=620, justify="left").grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(0, 5))
        return widget

    def _mode_page(self, f: ttk.Frame) -> None:
        r = self._section_title(f, "Competition mode", "Režim soutěže", "Choose a managed event or a clean judge-only replay screen.", "Vyber správu závodu, nebo čistou rozhodcovskou obrazovku.")
        self.vars["enabled"] = tk.BooleanVar(value=self.working.competition.enabled)
        self.vars["language"] = tk.StringVar(value=self.working.general.language)
        self._row(f, r, "Enable competition management", "Zapnout správu soutěže", self.vars["enabled"], "check"); r += 1
        self._row(f, r, "Application language", "Jazyk aplikace", self.vars["language"], "combo", ("en", "cs"))

    def _athletes_page(self, f: ttk.Frame) -> None:
        r = self._section_title(f, "Athletes", "Závodníci", "Boys and Girls are managed separately and rotate one athlete at a time.", "Chlapci a dívky se spravují odděleně a střídají se po jednom závodníkovi.")
        c = self.working.competition
        self.vars.update({"boys": tk.BooleanVar(value=c.boys_enabled), "girls": tk.BooleanVar(value=c.girls_enabled), "boys_count": tk.IntVar(value=c.boys_competitors), "girls_count": tk.IntVar(value=c.girls_competitors), "active_group": tk.StringVar(value=c.active_group)})
        self._row(f, r, "Enable Boys", "Zapnout chlapce", self.vars["boys"], "check"); r += 1
        self._row(f, r, "Boys athletes", "Počet chlapců", self.vars["boys_count"]); r += 1
        self._row(f, r, "Enable Girls", "Zapnout dívky", self.vars["girls"], "check"); r += 1
        self._row(f, r, "Girls athletes", "Počet dívek", self.vars["girls_count"]); r += 1
        self._row(f, r, "Start with group", "Začít skupinou", self.vars["active_group"], "combo", ("Boys", "Girls"))

    def _attempts_page(self, f: ttk.Frame) -> None:
        r = self._section_title(f, "Attempts and final", "Pokusy a finále", "Every athlete completes attempt 1 before the field moves to attempt 2.", "Všichni dokončí první pokus, než pole přejde ke druhému.")
        c = self.working.competition
        self.vars.update({
            "qualification": tk.IntVar(value=c.default_attempts_per_competitor), "require": tk.BooleanVar(value=c.require_decision_before_continue),
            "final": tk.BooleanVar(value=c.final_round_enabled), "finalists": tk.IntVar(value=c.finalists_count), "final_attempts": tk.IntVar(value=c.final_attempts),
            "final_order": tk.StringVar(value=c.final_order), "overlay": tk.BooleanVar(value=c.next_athlete_overlay), "banner": tk.BooleanVar(value=c.show_state_banner),
        })
        self._row(f, r, "Qualification attempts", "Základní pokusy", self.vars["qualification"]); r += 1
        self._row(f, r, "Require decision before next athlete", "Vyžadovat rozhodnutí před dalším závodníkem", self.vars["require"], "check", desc_en="Normally leave this off; attempts continue as Not decided.", desc_cs="Obvykle nech vypnuté; pokusy pokračují jako Nerozhodnuto."); r += 2
        self._row(f, r, "Enable final round", "Zapnout finále", self.vars["final"], "check"); r += 1
        self._row(f, r, "Athletes advancing", "Počet postupujících", self.vars["finalists"]); r += 1
        self._row(f, r, "Additional final attempts", "Další finálové pokusy", self.vars["final_attempts"]); r += 1
        self._row(f, r, "Final order", "Pořadí ve finále", self.vars["final_order"], "combo", ("same", "reverse", "manual")); r += 1
        self._row(f, r, "Show next-athlete overlay", "Zobrazit dalšího závodníka", self.vars["overlay"], "check"); r += 1
        self._row(f, r, "Show competition banner", "Zobrazit banner soutěže", self.vars["banner"], "check")

    def _camera_page(self, f: ttk.Frame) -> None:
        r = self._section_title(f, "Camera and performance", "Kamera a výkon", "The preset changes preview and analysis workload without silently reducing evidence quality. Camera changes take effect after restart.", "Profil mění zátěž náhledu a analýzy bez skrytého snížení kvality důkazu. Změny kamery se projeví po restartu.")
        c = self.working.camera
        self.vars.update({"device": tk.IntVar(value=c.device_index), "width": tk.IntVar(value=c.width), "height": tk.IntVar(value=c.height), "fps": tk.DoubleVar(value=c.fps), "preset": tk.StringVar(value=self.working.performance.preset)})
        self._row(f, r, "Camera index (0, 1, …)", "Index kamery (0, 1, …)", self.vars["device"]); r += 1
        self._row(f, r, "Width", "Šířka", self.vars["width"]); r += 1
        self._row(f, r, "Height", "Výška", self.vars["height"]); r += 1
        self._row(f, r, "Requested FPS", "Požadované FPS", self.vars["fps"]); r += 1
        self._row(f, r, "Performance preset", "Výkonový profil", self.vars["preset"], "combo", ("quiet", "balanced", "high", "evidence", "custom"), desc_en="Quiet is best for an upset fan; Balanced is recommended for most laptops.", desc_cs="Quiet je nejlepší pro rozrušený ventilátor; Balanced je doporučený pro většinu notebooků.")

    def _storage_page(self, f: ttk.Frame) -> None:
        r = self._section_title(f, "Replay and storage", "Replay a úložiště", "These values control how much video is preserved around Freeze.", "Tyto hodnoty určují, kolik videa se uchová kolem zmrazení.")
        a, b = self.working.attempts, self.working.buffer
        self.vars.update({"buffer": tk.DoubleVar(value=b.duration_seconds), "pre": tk.DoubleVar(value=a.pre_seconds), "post": tk.DoubleVar(value=a.post_seconds), "retention": tk.DoubleVar(value=a.retention_minutes), "cache": tk.DoubleVar(value=a.max_cache_gb), "clear": tk.BooleanVar(value=self.working.competition.clear_temp_on_new_competition)})
        self._row(f, r, "Live buffer seconds", "Sekundy živého bufferu", self.vars["buffer"]); r += 1
        self._row(f, r, "Pre-roll seconds", "Sekundy před zmrazením", self.vars["pre"]); r += 1
        self._row(f, r, "Post-roll seconds", "Sekundy po zmrazení", self.vars["post"]); r += 1
        self._row(f, r, "Retention minutes", "Doba uchování v minutách", self.vars["retention"]); r += 1
        self._row(f, r, "Maximum cache GB", "Maximální cache v GB", self.vars["cache"]); r += 1
        self._row(f, r, "Clear old temporary recordings", "Vymazat staré dočasné záznamy", self.vars["clear"], "check")

    def _review_page(self, f: ttk.Frame) -> None:
        self._section_title(f, "Review", "Souhrn")
        self.review_text = tk.Text(f, height=20, wrap="word", borderwidth=0, state="disabled")
        self.review_text.grid(row=2, column=0, columnspan=2, sticky="nsew")
        f.rowconfigure(2, weight=1); f.columnconfigure(0, weight=1)

    def _show(self, index: int) -> None:
        index = max(0, min(len(self.pages) - 1, index))
        if 0 <= self.index < len(self.pages):
            self.pages[self.index].pack_forget()
        self.index = index
        self.pages[index].pack(fill="both", expand=True)
        titles = [self._txt("Competition mode", "Režim soutěže"), self._txt("Athletes", "Závodníci"), self._txt("Attempts and final", "Pokusy a finále"), self._txt("Camera and performance", "Kamera a výkon"), self._txt("Replay and storage", "Replay a úložiště"), self._txt("Review", "Souhrn")]
        self.title_var.set(titles[index])
        self.step_var.set(self._txt(f"Step {index + 1} of {len(self.pages)}", f"Krok {index + 1} z {len(self.pages)}"))
        self.back_button.configure(state="disabled" if index == 0 else "normal")
        self.next_button.configure(text=self.tr("wizard.finish") if index == len(self.pages) - 1 else self.tr("wizard.next"))
        if index == len(self.pages) - 1:
            self._update_review()

    def _next(self) -> None:
        if self.index < len(self.pages) - 1:
            self._show(self.index + 1)
            return
        try:
            c = self.working.competition
            c.enabled = bool(self.vars["enabled"].get()); self.working.general.language = str(self.vars["language"].get())
            c.boys_enabled = bool(self.vars["boys"].get()); c.girls_enabled = bool(self.vars["girls"].get())
            c.boys_competitors = int(self.vars["boys_count"].get()); c.girls_competitors = int(self.vars["girls_count"].get()); c.active_group = str(self.vars["active_group"].get())
            c.default_attempts_per_competitor = int(self.vars["qualification"].get()); c.require_decision_before_continue = bool(self.vars["require"].get())
            c.final_round_enabled = bool(self.vars["final"].get()); c.finalists_count = int(self.vars["finalists"].get()); c.final_attempts = int(self.vars["final_attempts"].get()); c.final_order = str(self.vars["final_order"].get())
            c.next_athlete_overlay = bool(self.vars["overlay"].get()); c.show_state_banner = bool(self.vars["banner"].get()); c.clear_temp_on_new_competition = bool(self.vars["clear"].get())
            cam = self.working.camera; cam.device_index = int(self.vars["device"].get()); cam.width = int(self.vars["width"].get()); cam.height = int(self.vars["height"].get()); cam.fps = float(self.vars["fps"].get())
            preset = str(self.vars["preset"].get())
            if preset != "custom": apply_performance_preset(self.working, preset)
            b, a = self.working.buffer, self.working.attempts
            b.duration_seconds = float(self.vars["buffer"].get()); a.pre_seconds = float(self.vars["pre"].get()); a.post_seconds = float(self.vars["post"].get()); a.retention_minutes = float(self.vars["retention"].get()); a.max_cache_gb = float(self.vars["cache"].get())
            self.working.validate()
            self.on_finish(deepcopy(self.working), bool(self.vars["clear"].get()))
            self.destroy()
        except Exception as exc:
            messagebox.showerror(self._txt("Invalid competition setup", "Neplatné nastavení soutěže"), str(exc), parent=self)

    def _update_review(self) -> None:
        enabled = bool(self.vars["enabled"].get())
        lines = [self._txt("Competition management: ", "Správa soutěže: ") + (self._txt("Enabled", "Zapnuta") if enabled else self._txt("Judge-only", "Pouze rozhodčí"))]
        if enabled:
            if self.vars["boys"].get(): lines.append(self._txt("Boys athletes: ", "Chlapci: ") + str(self.vars["boys_count"].get()))
            if self.vars["girls"].get(): lines.append(self._txt("Girls athletes: ", "Dívky: ") + str(self.vars["girls_count"].get()))
            lines.append(self._txt("Qualification attempts: ", "Základní pokusy: ") + str(self.vars["qualification"].get()))
            lines.append(self._txt("Decision required: ", "Rozhodnutí povinné: ") + ("Yes" if self.vars["require"].get() else "No"))
            if self.vars["final"].get(): lines.append(self._txt("Final: top ", "Finále: top ") + f"{self.vars['finalists'].get()}, +{self.vars['final_attempts'].get()} attempts")
        lines += [f"Camera: index {self.vars['device'].get()} · {self.vars['width'].get()}×{self.vars['height'].get()} · {self.vars['fps'].get()} FPS", self._txt("Performance: ", "Výkon: ") + str(self.vars["preset"].get()), self._txt("Replay: ", "Replay: ") + f"{self.vars['pre'].get()} s pre / {self.vars['post'].get()} s post / {self.vars['retention'].get()} min"]
        self.review_text.configure(state="normal"); self.review_text.delete("1.0", "end"); self.review_text.insert("1.0", "\n\n".join(lines)); self.review_text.configure(state="disabled")
