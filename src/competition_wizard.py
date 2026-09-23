from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import date
import tkinter as tk
from tkinter import ttk

from .adjudication import AthleteContext
from .atletika_online import AtletikaEvent, AtletikaImportDialog, JumpRoster
from .competition_setup import CompetitionSetupModel, CompetitionTemplate, RecordingDisposition, WizardReadiness
from .config import AppConfig, CompetitionConfig
from .i18n import Translator
from .roster_editor import RosterEditor
from .theme import ask_themed_yes_no, configure_popup, show_themed_info


class CompetitionWizard(tk.Toplevel):
    """Guided competition setup."""

    SETUP_STEPS = ("format", "groups", "attempts", "aids", "review")

    def __init__(
        self,
        parent: tk.Misc,
        config: AppConfig,
        on_finish: Callable[[CompetitionConfig, RecordingDisposition], None],
        *,
        readiness_provider: Callable[[], WizardReadiness] | None = None,
        on_open_settings: Callable[[], tk.Toplevel | None] | None = None,
        on_camera_help: Callable[[], tk.Toplevel | None] | None = None,
        initial_roster: list[AthleteContext] | None = None,
        include_roster_on_finish: bool = False,
    ) -> None:
        super().__init__(parent)
        configure_popup(self, parent)
        self.model = CompetitionSetupModel(config.competition)
        self.on_finish = on_finish
        self.readiness_provider = readiness_provider or (lambda: WizardReadiness(
            config.general.language, False, 0, 0.0, config.camera.fps, "—", "", 0, 0.0,
            0, int(config.attempts.max_cache_gb * 1024 ** 3), 0,
        ))
        self.on_open_settings = on_open_settings
        self.on_camera_help = on_camera_help
        self.include_roster_on_finish = include_roster_on_finish
        self.lang = config.general.language
        self.tr = Translator(self.lang)
        self.setup_index = 0
        self.recording_disposition = tk.StringVar(self, value="")
        self.vars: dict[str, tk.Variable] = {}
        self.field_widgets: dict[str, tk.Widget] = {}
        self.error_var = tk.StringVar(self, value="")
        self._refresh_after: str | None = None
        self.rosters = self._initial_rosters(initial_roster or [], config.competition)
        self.model.competition.boys_competitors = len(self.rosters["Boys"])
        self.model.competition.girls_competitors = len(self.rosters["Girls"])
        self._build_vars()

        self.title(self.tr("wizard.title"))
        self.geometry("1100x720")
        self.minsize(1000, 660)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_shell()
        self._render()

    @staticmethod
    def _placeholder(group: str, number: int) -> AthleteContext:
        return AthleteContext(
            athlete_id=f"{group}:{number}", group=group, category=group,
            competitor_number=number, start_order=number, bib=str(number),
        )

    def _initial_rosters(self, initial: list[AthleteContext], competition: CompetitionConfig) -> dict[str, list[AthleteContext]]:
        rosters: dict[str, list[AthleteContext]] = {"Boys": [], "Girls": []}
        for item in initial:
            group = item.group or item.category
            if group in rosters:
                rosters[group].append(AthleteContext(**asdict(item)))
        for group, count in (("Boys", competition.boys_competitors), ("Girls", competition.girls_competitors)):
            rosters[group].sort(key=lambda athlete: (athlete.start_order or athlete.competitor_number, athlete.competitor_number))
            target_count = max(count, len(rosters[group]))
            while len(rosters[group]) < target_count:
                rosters[group].append(self._placeholder(group, len(rosters[group]) + 1))
            self._renumber_roster(group, rosters)
        return rosters

    @staticmethod
    def _renumber_roster(group: str, rosters: dict[str, list[AthleteContext]]) -> None:
        for number, athlete in enumerate(rosters[group], start=1):
            athlete.group = group
            athlete.category = athlete.category or group
            athlete.competitor_number = number
            athlete.start_order = number
            athlete.athlete_id = athlete.external_id or athlete.athlete_id or f"{group}:{number}"

    def _resize_roster(self, group: str, count: int) -> None:
        roster = self.rosters[group]
        while len(roster) < count:
            roster.append(self._placeholder(group, len(roster) + 1))
        del roster[count:]
        self._renumber_roster(group, self.rosters)

    def _build_vars(self) -> None:
        c = self.model.competition
        event_date = c.competition_date or date.today().isoformat()
        event_name = c.competition_name or f"Long jump — {event_date}"
        self.vars = {
            "competition_name": tk.StringVar(self, value=event_name),
            "competition_date": tk.StringVar(self, value=event_date),
            "boys": tk.BooleanVar(self, value=c.boys_enabled),
            "girls": tk.BooleanVar(self, value=c.girls_enabled),
            "boys_count": tk.StringVar(self, value=str(c.boys_competitors)),
            "girls_count": tk.StringVar(self, value=str(c.girls_competitors)),
            "active_group": tk.StringVar(self, value=c.active_group),
            "qualification": tk.StringVar(self, value=str(c.default_attempts_per_competitor)),
            "final": tk.BooleanVar(self, value=c.final_round_enabled),
            "finalists": tk.StringVar(self, value=str(c.finalists_count)),
            "final_attempts": tk.StringVar(self, value=str(c.final_attempts)),
            "final_order": tk.StringVar(self, value=c.final_order),
            "require": tk.BooleanVar(self, value=c.require_decision_before_continue),
            "overlay": tk.BooleanVar(self, value=c.next_athlete_overlay),
            "banner": tk.BooleanVar(self, value=c.show_state_banner),
            "distance": tk.BooleanVar(self, value=c.prompt_distance_after_valid),
            "wind": tk.BooleanVar(self, value=c.prompt_wind_after_valid),
        }

    def _build_shell(self) -> None:
        self.shell = ttk.Frame(self, style="App.TFrame", padding=18)
        self.shell.pack(fill="both", expand=True)
        header = ttk.Frame(self.shell, style="App.TFrame")
        header.pack(fill="x", pady=(0, 14))
        self.header_title = ttk.Label(header, style="WizardHeroTitle.TLabel")
        self.header_title.pack(anchor="w")
        self.header_desc = ttk.Label(header, style="WizardHeroDesc.TLabel", wraplength=900, justify="left")
        self.header_desc.pack(anchor="w", pady=(3, 0))
        self.body = ttk.Frame(self.shell, style="App.TFrame")
        self.body.pack(fill="both", expand=True)
        self.footer = ttk.Frame(self.shell, style="Toolbar.TFrame", padding=(10, 8))
        self.footer.pack(fill="x", pady=(14, 0))

    def _clear(self, frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _render(self) -> None:
        self._cancel_refresh()
        self._clear(self.body)
        self._clear(self.footer)
        self.error_var.set("")
        self._render_setup()

    def _render_setup(self) -> None:
        self.field_widgets = {}
        step = self.SETUP_STEPS[self.setup_index]
        self.header_title.configure(text=self.tr(f"wizard.step.{step}.title"))
        self.header_desc.configure(text=self.tr(f"wizard.step.{step}.desc"))
        rail = ttk.Frame(self.body, style="WizardRail.TFrame", padding=8)
        rail.pack(side="left", fill="y", padx=(0, 14))
        for index, key in enumerate(self.SETUP_STEPS):
            style = "WizardRailActive.TLabel" if index == self.setup_index else "WizardRail.TLabel"
            ttk.Label(rail, text=f"{index + 1:02d}  {self.tr(f'wizard.step.{key}.short')}", style=style).pack(fill="x", pady=2)
        content = ttk.Frame(self.body, style="Panel.TFrame", padding=22)
        content.pack(side="left", fill="both", expand=True)
        getattr(self, f"_page_{step}")(content)
        ttk.Label(self.footer, textvariable=self.error_var, style="Warning.TLabel").pack(side="left", padx=(8, 0))
        ttk.Button(self.footer, text=self.tr("wizard.cancel"), command=self._close).pack(side="left")
        label = self.tr("wizard.finish") if step == "review" else self.tr("wizard.next")
        ttk.Button(self.footer, text=label, style="Primary.TButton", command=self._setup_next).pack(side="right")
        if self.setup_index > 0:
            ttk.Button(self.footer, text=self.tr("wizard.back"), command=self._setup_back).pack(side="right", padx=(8, 0))
        # The review page is intentionally static after confirmation.  The
        # old periodic rebuild destroyed and recreated the widgets every 1.2s,
        # which looked like flashing and could steal focus from the final
        # confirmation button.  The existing Refresh action remains available
        # for an explicit readiness check.

    def _page_format(self, parent: ttk.Frame) -> None:
        details = ttk.Frame(parent, style="WizardCard.TFrame", padding=16)
        details.pack(fill="x", pady=(0, 12))
        details.columnconfigure(1, weight=1)
        ttk.Label(details, text=self.tr("wizard.event.name"), style="Text.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        name = ttk.Entry(details, textvariable=self.vars["competition_name"])
        name.grid(row=0, column=1, sticky="ew")
        self.field_widgets["competition_name"] = name
        ttk.Label(details, text=self.tr("wizard.event.date"), style="Text.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        event_date = ttk.Entry(details, textvariable=self.vars["competition_date"], width=16)
        event_date.grid(row=1, column=1, sticky="w", pady=(10, 0))
        self.field_widgets["competition_date"] = event_date
        ttk.Button(
            details, text=self.tr("wizard.online.button"), style="Secondary.TButton",
            command=self._open_atletika_import,
        ).grid(row=1, column=1, sticky="e", pady=(10, 0))
        ttk.Label(details, text=self.tr("wizard.online.hint"), style="Muted.TLabel").grid(
            row=2, column=1, sticky="w", pady=(7, 0),
        )
        for row, template in enumerate(("simple", "final", "judge_only")):
            card = ttk.Frame(parent, style="WizardCard.TFrame", padding=16)
            card.pack(fill="x", pady=(0, 10))
            ttk.Label(card, text=self.tr(f"wizard.template.{template}.title"), style="WizardCardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, text=self.tr(f"wizard.template.{template}.desc"), style="Muted.TLabel", wraplength=680, justify="left").pack(anchor="w", pady=(5, 10))
            selected = self.model.template == template
            ttk.Button(card, text=self.tr("wizard.template.selected") if selected else self.tr("wizard.template.choose"), style="Primary.TButton" if selected else "Secondary.TButton", command=lambda value=template: self._choose_template(value)).pack(anchor="e")

    def _open_atletika_import(self) -> None:
        try:
            selected_date = date.fromisoformat(str(self.vars["competition_date"].get()).strip())
        except ValueError:
            self.error_var.set(self.tr("wizard.error.competition_date"))
            self.field_widgets["competition_date"].focus_set()
            return
        self.grab_release()
        dialog = AtletikaImportDialog(self, self.lang, selected_date, self._accept_atletika_import)
        try:
            self.wait_window(dialog)
        finally:
            if self.winfo_exists():
                self.grab_set()

    def _accept_atletika_import(self, event: AtletikaEvent, selected: list[JumpRoster]) -> None:
        imported: dict[str, list[AthleteContext]] = {"Boys": [], "Girls": []}
        identities: dict[str, set[str]] = {"Boys": set(), "Girls": set()}
        for roster in selected:
            for athlete in roster.athletes:
                identity = athlete.external_id or f"{athlete.name.casefold()}|{athlete.club.casefold()}"
                if identity in identities[roster.group]:
                    continue
                identities[roster.group].add(identity)
                imported[roster.group].append(AthleteContext(**asdict(athlete)))
        self.vars["competition_name"].set(event.name)
        for group, athletes in imported.items():
            if not athletes:
                continue
            self.rosters[group] = athletes
            self._renumber_roster(group, self.rosters)
            key = "boys" if group == "Boys" else "girls"
            self.vars[key].set(True)
            self.vars[f"{key}_count"].set(str(len(athletes)))
        self._sync_model(quiet=True)
        self._render()

    def _choose_template(self, template: CompetitionTemplate) -> None:
        self._sync_model(quiet=True)
        self.model.apply_template(template)
        self._build_vars()
        self._render()

    def _page_groups(self, parent: ttk.Frame) -> None:
        if not self.model.competition.enabled:
            self._judge_only_note(parent)
            return
        for key, count_key, group in (("boys", "boys_count", "Boys"), ("girls", "girls_count", "Girls")):
            card = ttk.Frame(parent, style="WizardCard.TFrame", padding=16)
            card.pack(fill="x", pady=(0, 10))
            enabled = ttk.Checkbutton(card, text=self.tr(f"wizard.groups.{key}"), variable=self.vars[key], command=self._groups_changed)
            enabled.grid(row=0, column=0, sticky="w")
            self.field_widgets.setdefault("groups", enabled)
            ttk.Label(card, text=self.tr("wizard.groups.count"), style="Muted.TLabel").grid(row=0, column=1, padx=(20, 8))
            count = ttk.Spinbox(card, from_=1, to=200, textvariable=self.vars[count_key], width=8)
            count.grid(row=0, column=2)
            self.field_widgets[count_key] = count
            ttk.Button(
                card, text=self.tr("wizard.roster.edit"), style="Secondary.TButton",
                command=lambda selected=group: self._open_roster_editor(selected),
            ).grid(row=1, column=0, sticky="w", pady=(10, 0))
            preview = self._roster_preview(group)
            ttk.Label(card, text=preview, style="Muted.TLabel", wraplength=560, justify="left").grid(
                row=1, column=1, columnspan=2, sticky="w", padx=(20, 0), pady=(10, 0),
            )
        row = ttk.Frame(parent, style="Panel.TFrame")
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text=self.tr("wizard.groups.start"), style="Text.TLabel").pack(side="left")
        group_keys = ("Boys", "Girls")
        group_values = (self.tr("wizard.groups.boys"), self.tr("wizard.groups.girls"))
        display = tk.StringVar(self, value=group_values[group_keys.index(str(self.vars["active_group"].get()))])
        combo = ttk.Combobox(row, state="readonly", width=18, textvariable=display, values=group_values)
        combo.pack(side="left", padx=(12, 0))
        combo.bind("<<ComboboxSelected>>", lambda _event: self.vars["active_group"].set(group_keys[group_values.index(display.get())]))

    def _groups_changed(self) -> None:
        self._sync_model(quiet=True)
        self.model.normalize_dependencies()
        self.vars["active_group"].set(self.model.competition.active_group)

    def _roster_preview(self, group: str) -> str:
        named = [item.name.strip() for item in self.rosters[group] if item.name.strip()]
        if not named:
            return self.tr("wizard.roster.placeholder_summary", count=len(self.rosters[group]))
        shown = ", ".join(named[:3])
        if len(named) > 3:
            shown += self.tr("wizard.roster.more", count=len(named) - 3)
        return shown

    def _open_roster_editor(self, group: str) -> None:
        if not self._sync_model(quiet=True):
            self.error_var.set(self.tr("wizard.error.number"))
            return
        key = "boys_count" if group == "Boys" else "girls_count"
        self._resize_roster(group, int(str(self.vars[key].get())))
        self.grab_release()
        editor = RosterEditor(
            self, {}, self.lang, group, self.rosters[group],
            lambda athletes, selected=group: self._accept_roster(selected, athletes),
        )
        try:
            self.wait_window(editor)
        finally:
            if self.winfo_exists():
                self.grab_set()

    def _accept_roster(self, group: str, athletes: list[AthleteContext]) -> None:
        if not athletes:
            raise ValueError(self.tr("wizard.error.athlete_count"))
        self.rosters[group] = [AthleteContext(**asdict(item)) for item in athletes]
        self._renumber_roster(group, self.rosters)
        key = "boys_count" if group == "Boys" else "girls_count"
        self.vars[key].set(str(len(athletes)))
        self._render()

    def _page_attempts(self, parent: ttk.Frame) -> None:
        if not self.model.competition.enabled:
            self._judge_only_note(parent)
            return
        self._field(parent, "wizard.attempts.qualification", "qualification", 1, 20)
        ttk.Checkbutton(parent, text=self.tr("wizard.attempts.final"), variable=self.vars["final"], command=self._render).pack(anchor="w", pady=(12, 10))
        if bool(self.vars["final"].get()):
            self._field(parent, "wizard.attempts.finalists", "finalists", 1, 200)
            self._field(parent, "wizard.attempts.final_attempts", "final_attempts", 1, 20)
            order = ttk.Frame(parent, style="Panel.TFrame")
            order.pack(fill="x", pady=8)
            ttk.Label(order, text=self.tr("wizard.attempts.order"), style="Text.TLabel").pack(side="left")
            values = tuple(self.tr(f"wizard.order.{key}") for key in ("same", "reverse", "manual"))
            display = tk.StringVar(self, value=self.tr(f"wizard.order.{self.vars['final_order'].get()}"))
            combo = ttk.Combobox(order, state="readonly", values=values, textvariable=display, width=24)
            combo.pack(side="left", padx=(12, 0))
            combo.bind("<<ComboboxSelected>>", lambda _event: self.vars["final_order"].set(("same", "reverse", "manual")[values.index(display.get())]))

    def _field(self, parent: ttk.Frame, label_key: str, variable: str, minimum: int, maximum: int) -> None:
        row = ttk.Frame(parent, style="WizardCard.TFrame", padding=14)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=self.tr(label_key), style="Text.TLabel").pack(side="left")
        widget = ttk.Spinbox(row, from_=minimum, to=maximum, textvariable=self.vars[variable], width=8)
        widget.pack(side="right")
        self.field_widgets[variable] = widget

    def _page_aids(self, parent: ttk.Frame) -> None:
        if not self.model.competition.enabled:
            self._judge_only_note(parent)
            return
        self._aid_card(parent, "require", "wizard.aids.require.title", "wizard.aids.require.desc")
        self._aid_card(parent, "overlay", "wizard.aids.overlay.title", "wizard.aids.overlay.desc")
        self._aid_card(parent, "banner", "wizard.aids.banner.title", "wizard.aids.banner.desc")
        self._aid_card(parent, "distance", "wizard.aids.distance.title", "wizard.aids.distance.desc")
        if bool(self.vars["distance"].get()):
            self._aid_card(parent, "wind", "wizard.aids.wind.title", "wizard.aids.wind.desc")
        if bool(self.vars["require"].get()):
            ttk.Label(parent, text=self.tr("wizard.aids.require.warning"), style="Warning.TLabel", wraplength=700, justify="left").pack(anchor="w", pady=(6, 0))

    def _aid_card(self, parent: ttk.Frame, variable: str, title_key: str, desc_key: str) -> None:
        card = ttk.Frame(parent, style="WizardCard.TFrame", padding=14)
        card.pack(fill="x", pady=5)
        ttk.Checkbutton(card, text=self.tr(title_key), variable=self.vars[variable], command=self._render if variable == "require" else None).pack(anchor="w")
        ttk.Label(card, text=self.tr(desc_key), style="Muted.TLabel", wraplength=700, justify="left").pack(anchor="w", pady=(4, 0))

    def _page_review(self, parent: ttk.Frame) -> None:
        self._sync_model(quiet=True)
        c = self.model.competition
        summary = ttk.Frame(parent, style="WizardCard.TFrame", padding=16)
        summary.pack(fill="x")
        ttk.Label(summary, text=self.tr("wizard.review.summary"), style="WizardCardTitle.TLabel").pack(anchor="w")
        lines = [
            self.tr("wizard.review.name", name=c.competition_name, date=c.competition_date),
            self.tr(f"wizard.template.{self.model.template}.title"),
        ]
        if c.enabled:
            if c.boys_enabled:
                lines.append(self.tr("wizard.review.group", group=self.tr("wizard.groups.boys"), count=c.boys_competitors))
            if c.girls_enabled:
                lines.append(self.tr("wizard.review.group", group=self.tr("wizard.groups.girls"), count=c.girls_competitors))
            lines.append(self.tr("wizard.review.attempts", count=c.default_attempts_per_competitor))
            if c.final_round_enabled:
                lines.append(self.tr("wizard.review.final", finalists=c.finalists_count, attempts=c.final_attempts, order=self.tr(f"wizard.order.{c.final_order}")))
            lines.append(self.tr("wizard.review.capacity", count=self.model.expected_attempt_cells()))
        ttk.Label(summary, text="\n".join(f"• {line}" for line in lines), style="Muted.TLabel", justify="left").pack(anchor="w", pady=(8, 0))
        ready = self.readiness_provider()
        readiness = ttk.Frame(parent, style="WizardCard.TFrame", padding=16)
        readiness.pack(fill="x", pady=(12, 0))
        ttk.Label(readiness, text=self.tr("wizard.readiness.title"), style="WizardCardTitle.TLabel").grid(row=0, column=0, sticky="w")
        self._readiness_badge(readiness, ready).grid(row=0, column=1, sticky="e")
        readiness.columnconfigure(0, weight=1)
        detail = self.tr("wizard.readiness.detail", source=ready.source_description, fps=ready.capture_fps, buffer=ready.buffer_seconds, cache=ready.cache_bytes / 1024 ** 2)
        ttk.Label(readiness, text=detail, style="Muted.TLabel", wraplength=650, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", pady=(7, 8))
        issues = ready.issue_keys()
        if issues:
            ttk.Label(
                readiness,
                text="\n".join(f"• {self.tr(f'wizard.readiness.issue.{issue}')}" for issue in issues),
                style="Warning.TLabel", wraplength=650, justify="left",
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))
        actions = ttk.Frame(readiness, style="Panel.TFrame")
        actions.grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Button(actions, text=self.tr("wizard.readiness.refresh"), command=self._render).pack(side="left")
        if self.on_camera_help:
            ttk.Button(actions, text=self.tr("wizard.readiness.help"), command=self._open_camera_help).pack(side="left", padx=(7, 0))
        if self.on_open_settings:
            ttk.Button(actions, text=self.tr("wizard.readiness.settings"), command=self._open_settings).pack(side="left", padx=(7, 0))
        if ready.temporary_recording_count:
            recordings = ttk.Frame(parent, style="WizardCard.TFrame", padding=16)
            recordings.pack(fill="x", pady=(12, 0))
            ttk.Label(recordings, text=self.tr("wizard.recordings.title", count=ready.temporary_recording_count), style="WizardCardTitle.TLabel").pack(anchor="w")
            ttk.Label(recordings, text=self.tr("wizard.recordings.desc"), style="Muted.TLabel", wraplength=680, justify="left").pack(anchor="w", pady=(5, 8))
            ttk.Radiobutton(recordings, text=self.tr("wizard.recordings.keep"), variable=self.recording_disposition, value="keep").pack(anchor="w")
            ttk.Radiobutton(recordings, text=self.tr("wizard.recordings.clear"), variable=self.recording_disposition, value="clear").pack(anchor="w")

    def _judge_only_note(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text=self.tr("wizard.judge_only.note"), style="Muted.TLabel", wraplength=700, justify="left").pack(anchor="w")

    def _readiness_badge(self, parent: tk.Misc, ready: WizardReadiness) -> ttk.Label:
        style = {"ready": "WizardReady.TLabel", "warming": "WizardWarm.TLabel", "warning": "WizardDanger.TLabel"}[ready.level]
        return ttk.Label(parent, text=self.tr(f"wizard.readiness.{ready.level}"), style=style)

    def _setup_back(self) -> None:
        if self.setup_index == 0:
            return
        self._sync_model(quiet=True)
        self.setup_index -= 1
        self._render()

    def _setup_next(self) -> None:
        step = self.SETUP_STEPS[self.setup_index]
        if not self._sync_model():
            return
        errors = self.model.validate_step(step)
        if errors:
            field, code = next(iter(errors.items()))
            self.error_var.set(self.tr(f"wizard.error.{code}"))
            widget = self.field_widgets.get(field)
            if widget is not None:
                widget.focus_set()
            return
        if step != "review":
            self.setup_index += 1
            self._render()
            return
        ready = self.readiness_provider()
        disposition = self.recording_disposition.get()
        if ready.temporary_recording_count and disposition not in {"keep", "clear"}:
            self.error_var.set(self.tr("wizard.error.recording_choice"))
            return
        if ready.level == "warning" and not ask_themed_yes_no(
            self, self.tr("wizard.warning.title"), self.tr("wizard.warning.desc"),
            yes=self.tr("wizard.warning.start"), no=self.tr("wizard.warning.back"),
        ):
            return
        try:
            built = self.model.build_config()
            enabled_groups = [
                group for group, enabled in (
                    ("Boys", built.boys_enabled), ("Girls", built.girls_enabled),
                ) if enabled
            ]
            roster = [
                AthleteContext(**asdict(item))
                for group in enabled_groups
                for item in self.rosters[group]
            ]
            if self.include_roster_on_finish:
                self.on_finish(built, "clear" if disposition == "clear" else "keep", roster)
            else:
                self.on_finish(built, "clear" if disposition == "clear" else "keep")
            self._close()
        except Exception as exc:
            show_themed_info(self, self.tr("wizard.invalid.title"), str(exc))

    def _sync_model(self, *, quiet: bool = False) -> bool:
        c = self.model.competition
        try:
            c.competition_name = str(self.vars["competition_name"].get()).strip()
            c.competition_date = str(self.vars["competition_date"].get()).strip()
            c.boys_enabled = bool(self.vars["boys"].get())
            c.girls_enabled = bool(self.vars["girls"].get())
            c.boys_competitors = int(str(self.vars["boys_count"].get()))
            c.girls_competitors = int(str(self.vars["girls_count"].get()))
            if 1 <= c.boys_competitors <= 200:
                self._resize_roster("Boys", c.boys_competitors)
            if 1 <= c.girls_competitors <= 200:
                self._resize_roster("Girls", c.girls_competitors)
            c.active_group = str(self.vars["active_group"].get())
            c.default_attempts_per_competitor = int(str(self.vars["qualification"].get()))
            c.final_round_enabled = bool(self.vars["final"].get())
            c.finalists_count = int(str(self.vars["finalists"].get()))
            c.final_attempts = int(str(self.vars["final_attempts"].get()))
            c.final_order = str(self.vars["final_order"].get())
            c.require_decision_before_continue = bool(self.vars["require"].get())
            c.next_athlete_overlay = bool(self.vars["overlay"].get())
            c.show_state_banner = bool(self.vars["banner"].get())
            c.prompt_distance_after_valid = bool(self.vars["distance"].get())
            c.prompt_wind_after_valid = bool(self.vars["wind"].get()) and c.prompt_distance_after_valid
            self.model.normalize_dependencies()
            self.vars["active_group"].set(c.active_group)
            return True
        except (TypeError, ValueError, tk.TclError):
            if not quiet:
                self.error_var.set(self.tr("wizard.error.number"))
            return False

    def _open_camera_help(self) -> None:
        if self.on_camera_help:
            self.grab_release()
            dialog = None
            try:
                dialog = self.on_camera_help()
                if dialog is not None:
                    self.wait_window(dialog)
                current_grab = self.grab_current()
                if current_grab is not None and current_grab is not self:
                    self.wait_window(current_grab)
            except tk.TclError:
                pass
            finally:
                if self.winfo_exists():
                    self.grab_set()

    def _open_settings(self) -> None:
        if not self.on_open_settings:
            return
        self._sync_model(quiet=True)
        self.grab_release()
        dialog = self.on_open_settings()
        if dialog is not None:
            try:
                self.wait_window(dialog)
            except tk.TclError:
                pass
        if not self.winfo_exists():
            return
        ready = self.readiness_provider()
        if ready.language != self.lang:
            self.lang = ready.language
            self.tr.set_language(self.lang)
            self.title(self.tr("wizard.title"))
        self.grab_set()
        self._render()

    def _schedule_refresh(self) -> None:
        self._cancel_refresh()
        self._refresh_after = self.after(1200, self._refresh_visible_readiness)

    def _refresh_visible_readiness(self) -> None:
        self._refresh_after = None
        if self.SETUP_STEPS[self.setup_index] == "review":
            self._render()

    def _cancel_refresh(self) -> None:
        if self._refresh_after is not None:
            try:
                self.after_cancel(self._refresh_after)
            except tk.TclError:
                pass
            self._refresh_after = None

    def _close(self) -> None:
        self._cancel_refresh()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
