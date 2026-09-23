from __future__ import annotations

from dataclasses import asdict
import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable

from .adjudication import AthleteContext
from .i18n import Translator
from .theme import configure_popup, show_themed_info


class RosterEditor(tk.Toplevel):
    """Small native editor for the current group's start order."""

    def __init__(
        self,
        parent: tk.Misc,
        palette: dict[str, str],
        language: str,
        group: str,
        athletes: Iterable[AthleteContext],
        on_save: Callable[[list[AthleteContext]], None],
    ) -> None:
        super().__init__(parent)
        configure_popup(self, parent)
        self.tr = Translator(language)
        self.title(self.tr("wizard.roster.edit").rstrip("…"))
        self.geometry("650x520")
        self.minsize(520, 380)
        self.transient(parent)
        self.grab_set()
        self.group = group
        self.on_save = on_save
        self._athletes = [AthleteContext(**asdict(item)) for item in athletes]
        self._build()
        self._refresh()

    def _build(self) -> None:
        shell = ttk.Frame(self, padding=14)
        shell.pack(fill="both", expand=True)
        group_name = self.tr(f"wizard.groups.{self.group.lower()}")
        ttk.Label(shell, text=self.tr("wizard.roster.title", group=group_name), style="WizardCardTitle.TLabel").pack(anchor="w")
        ttk.Label(shell, text=self.tr("wizard.roster.desc"), style="Muted.TLabel").pack(anchor="w", pady=(3, 10))
        content = ttk.Frame(shell)
        content.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(content, columns=("order", "name", "club", "bib"), show="headings", selectmode="browse")
        for column, heading, width in (
            ("order", self.tr("wizard.roster.order"), 55),
            ("name", self.tr("wizard.roster.name"), 250),
            ("club", self.tr("wizard.roster.club"), 200),
            ("bib", self.tr("wizard.roster.bib"), 80),
        ):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        scrollbar = ttk.Scrollbar(content, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(10, 4))
        ttk.Button(actions, text=self.tr("wizard.roster.move_up"), command=lambda: self._move(-1)).pack(side="left")
        ttk.Button(actions, text=self.tr("wizard.roster.move_down"), command=lambda: self._move(1)).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text=self.tr("wizard.roster.remove"), command=self._remove).pack(side="left", padx=(14, 0))
        form = ttk.Frame(shell)
        form.pack(fill="x", pady=(10, 4))
        self.name_var = tk.StringVar(self)
        self.club_var = tk.StringVar(self)
        self.bib_var = tk.StringVar(self)
        for column, label, variable in (
            (0, self.tr("wizard.roster.name"), self.name_var),
            (1, self.tr("wizard.roster.club"), self.club_var),
            (2, self.tr("wizard.roster.bib"), self.bib_var),
        ):
            ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else 8, 0))
            ttk.Entry(form, textvariable=variable).grid(row=1, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            form.columnconfigure(column, weight=1)
        ttk.Button(form, text=self.tr("wizard.roster.add"), style="Primary.TButton", command=self._add).grid(row=1, column=3, padx=(4, 0), sticky="ew")
        ttk.Button(form, text=self.tr("wizard.roster.update"), command=self._update).grid(row=1, column=4, padx=(6, 0), sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._load_selected)
        self.tree.bind("<Double-1>", self._load_selected)
        footer = ttk.Frame(shell)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text=self.tr("wizard.roster.cancel"), command=self.destroy).pack(side="right")
        ttk.Button(footer, text=self.tr("wizard.roster.save"), style="Primary.TButton", command=self._save).pack(side="right", padx=(0, 8))

    def _refresh(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, athlete in enumerate(self._athletes, start=1):
            self.tree.insert("", "end", iid=str(index - 1), values=(index, athlete.name or "—", athlete.club or "—", athlete.bib or "—"))
        if self._athletes:
            self.tree.selection_set("0")
            self.tree.focus("0")

    def _selected_index(self) -> int | None:
        selected = self.tree.selection()
        if not selected:
            return None
        try:
            return int(selected[0])
        except ValueError:
            return None

    def _move(self, delta: int) -> None:
        index = self._selected_index()
        if index is None:
            return
        target = max(0, min(len(self._athletes) - 1, index + delta))
        if target == index:
            return
        self._athletes[index], self._athletes[target] = self._athletes[target], self._athletes[index]
        self._refresh()
        self.tree.selection_set(str(target))
        self.tree.focus(str(target))

    def _remove(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        self._athletes.pop(index)
        self._refresh()

    def _add(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            show_themed_info(self, self.tr("wizard.roster.name"), self.tr("wizard.roster.name_required"))
            return
        self._athletes.append(AthleteContext(
            athlete_id=f"{self.group}:{len(self._athletes) + 1}:{name}",
            group=self.group,
            category=self.group,
            name=name,
            club=self.club_var.get().strip(),
            bib=self.bib_var.get().strip(),
        ))
        self.name_var.set("")
        self.club_var.set("")
        self.bib_var.set("")
        self._refresh()
        self.tree.selection_set(str(len(self._athletes) - 1))
        self.tree.see(str(len(self._athletes) - 1))

    def _load_selected(self, _event: tk.Event | None = None) -> None:
        index = self._selected_index()
        if index is None or not 0 <= index < len(self._athletes):
            return
        athlete = self._athletes[index]
        self.name_var.set(athlete.name)
        self.club_var.set(athlete.club)
        self.bib_var.set(athlete.bib)

    def _update(self) -> None:
        index = self._selected_index()
        name = self.name_var.get().strip()
        if index is None:
            return
        if not name:
            show_themed_info(self, self.tr("wizard.roster.name"), self.tr("wizard.roster.name_required"))
            return
        athlete = self._athletes[index]
        athlete.name = name
        athlete.club = self.club_var.get().strip()
        athlete.bib = self.bib_var.get().strip()
        self._refresh()
        self.tree.selection_set(str(index))
        self.tree.focus(str(index))

    def _save(self) -> None:
        for number, athlete in enumerate(self._athletes, start=1):
            athlete.competitor_number = number
            athlete.start_order = number
            athlete.group = self.group
            athlete.category = athlete.category or self.group
        try:
            self.on_save(self._athletes)
        except Exception as exc:
            show_themed_info(self, "Athlete order", str(exc))
            return
        self.destroy()