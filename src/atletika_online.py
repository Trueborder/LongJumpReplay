from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html import unescape
import re
from threading import Thread
import tkinter as tk
from tkinter import ttk
from typing import Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .adjudication import AthleteContext
from .i18n import Translator
from .theme import configure_popup, show_themed_info


BASE_URL = "https://online.atletika.cz"
CALENDAR_URL = f"{BASE_URL}/kalendar/vysledky/1"
USER_AGENT = "LongJumpReplay/competition-import (+https://tomaspisar.cz)"


@dataclass(frozen=True, slots=True)
class AtletikaEvent:
    event_id: str
    date_text: str
    name: str
    place: str

    @property
    def url(self) -> str:
        return f"{BASE_URL}/vysledky/{self.event_id}"


@dataclass(frozen=True, slots=True)
class JumpRoster:
    label: str
    group: str
    athletes: tuple[AthleteContext, ...]


def _plain(value: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _fetch(url: str, timeout: float = 8.0) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "cs,en;q=0.8"})
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _row_includes_day(text: str, day: date) -> bool:
    normalized = " ".join(text.split())
    cross = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*-\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", normalized)
    if cross:
        start = date(int(cross[5]), int(cross[2]), int(cross[1]))
        end = date(int(cross[5]), int(cross[4]), int(cross[3]))
        return start <= day <= end
    same = re.search(r"(\d{1,2})\.\s*-\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", normalized)
    if same:
        start = date(int(same[4]), int(same[3]), int(same[1]))
        end = date(int(same[4]), int(same[3]), int(same[2]))
        return start <= day <= end
    single = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", normalized)
    return bool(single and date(int(single[3]), int(single[2]), int(single[1])) == day)


def parse_calendar_events(html: str, day: date) -> list[AtletikaEvent]:
    events: list[AtletikaEvent] = []
    seen: set[str] = set()
    rows = re.findall(r'<li\s+class="results__row"[^>]*>(.*?)</li>', html, flags=re.I | re.S)
    for row in rows:
        date_match = re.search(r'<span\s+class="results__date"[^>]*>(.*?)</span>', row, flags=re.I | re.S)
        info_match = re.search(r'<span\s+class="results__info"[^>]*>(.*?)</span>', row, flags=re.I | re.S)
        title_match = re.search(r'<strong[^>]*>(.*?)</strong>', info_match.group(1) if info_match else "", flags=re.I | re.S)
        if not date_match or not info_match or not title_match:
            continue
        date_text = _plain(date_match.group(1))
        if not _row_includes_day(date_text, day):
            continue
        links = re.findall(r'href="([^"]+)"', row, flags=re.I)
        event_id = ""
        for pattern in (r"/vysledky/(\d+)", r"/prihlasky/seznam-prihlasek(?:-akce)?/(\d+)", r"/Propozice/propozice/(\d+)"):
            event_id = next((match.group(1) for link in links if (match := re.search(pattern, link, flags=re.I))), "")
            if event_id:
                break
        if not event_id or event_id in seen:
            continue
        name = _plain(title_match.group(1))
        place = _plain(info_match.group(1)).removeprefix(name).strip(" ,")
        events.append(AtletikaEvent(event_id, date_text, name, place))
        seen.add(event_id)
    return events


def fetch_events(day: date) -> list[AtletikaEvent]:
    return parse_calendar_events(_fetch(CALENDAR_URL), day)


def _group_for_label(label: str) -> str:
    lowered = label.casefold()
    female = ("žákyn", "dorostenk", "juniork", "ženy", "dív", "women", "girls")
    return "Girls" if any(token in lowered for token in female) else "Boys"


def _parse_athletes(section: str, group: str) -> tuple[AthleteContext, ...]:
    athletes: list[AthleteContext] = []
    seen: set[str] = set()
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', section, flags=re.I | re.S):
        name_match = re.search(r'class="resultsEanLink"[^>]*>(.*?)</(?:a|span)>', row, flags=re.I | re.S)
        if not name_match:
            continue
        name = _plain(name_match.group(1))
        club_match = re.search(r'class="\s*athleteclub\s+noprint"[^>]*>(.*?)</span>', row, flags=re.I | re.S)
        club = _plain(club_match.group(1)) if club_match else ""
        external_match = re.search(r'/vysledky-atleta/\d+/(\d+)', row, flags=re.I)
        external_id = external_match.group(1) if external_match else ""
        identity = external_id or f"{name.casefold()}|{club.casefold()}"
        if not name or identity in seen:
            continue
        seen.add(identity)
        number = len(athletes) + 1
        athletes.append(AthleteContext(
            athlete_id=external_id or f"{group}:{number}:{name}", external_id=external_id,
            group=group, category=group, competitor_number=number, start_order=number,
            name=name, club=club,
        ))
    return tuple(athletes)


def parse_jump_rosters(html: str) -> list[JumpRoster]:
    rosters: list[JumpRoster] = []
    sections = re.findall(
        r'<h2\s+class="main-result-header"[^>]*>(.*?)</h2>(.*?)(?=<h2\s+class="main-result-header"|\Z)',
        html, flags=re.I | re.S,
    )
    for header, body in sections:
        label = _plain(header)
        folded = label.casefold()
        if "skok dalek" not in folded and "long jump" not in folded:
            continue
        group = _group_for_label(label)
        athletes = _parse_athletes(body, group)
        if athletes:
            rosters.append(JumpRoster(label, group, athletes))
    return rosters


def fetch_jump_rosters(event: AtletikaEvent) -> list[JumpRoster]:
    return parse_jump_rosters(_fetch(event.url))


class AtletikaImportDialog(tk.Toplevel):
    """Small non-blocking chooser for today's Czech Athletics long-jump lists."""

    def __init__(self, parent: tk.Misc, language: str, day: date, on_import: Callable[[AtletikaEvent, list[JumpRoster]], None]) -> None:
        super().__init__(parent)
        configure_popup(self, parent)
        self.tr = Translator(language)
        self.day = day
        self.on_import = on_import
        self.events: list[AtletikaEvent] = []
        self.rosters: list[JumpRoster] = []
        self.title(self.tr("wizard.online.title"))
        self.geometry("760x500")
        self.minsize(620, 420)
        self.transient(parent)
        self.grab_set()
        self.status = tk.StringVar(self, value=self.tr("wizard.online.loading_events"))
        self._build()
        self._start(self._load_events, self._events_ready)

    def _build(self) -> None:
        shell = ttk.Frame(self, padding=16)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=self.tr("wizard.online.heading"), style="WizardCardTitle.TLabel").pack(anchor="w")
        ttk.Label(shell, textvariable=self.status, style="Muted.TLabel", wraplength=700).pack(anchor="w", pady=(4, 10))
        self.tree = ttk.Treeview(shell, columns=("date", "name", "place"), show="headings", selectmode="browse", height=13)
        for key, width in (("date", 120), ("name", 300), ("place", 260)):
            self.tree.heading(key, text=self.tr(f"wizard.online.{key}"))
            self.tree.column(key, width=width, minwidth=80, stretch=key != "date")
        self.tree.pack(fill="both", expand=True)
        footer = ttk.Frame(shell)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text=self.tr("wizard.roster.cancel"), command=self.destroy).pack(side="right")
        self.action = ttk.Button(footer, text=self.tr("wizard.online.load_rosters"), style="Primary.TButton", command=self._load_selected, state="disabled")
        self.action.pack(side="right", padx=(0, 8))

    def _start(self, operation: Callable[[], object], callback: Callable[[object, Exception | None], None]) -> None:
        def worker() -> None:
            try:
                result, error = operation(), None
            except Exception as exc:
                result, error = None, exc
            try:
                self.after(0, callback, result, error)
            except tk.TclError:
                pass
        Thread(target=worker, name="atletika-import", daemon=True).start()

    def _load_events(self) -> list[AtletikaEvent]:
        return fetch_events(self.day)

    def _events_ready(self, result: object, error: Exception | None) -> None:
        if not self.winfo_exists():
            return
        if error:
            self.status.set(self.tr("wizard.online.offline"))
            return
        self.events = list(result or [])
        for index, event in enumerate(self.events):
            self.tree.insert("", "end", iid=str(index), values=(event.date_text, event.name, event.place))
        if not self.events:
            self.status.set(self.tr("wizard.online.none", date=self.day.isoformat()))
            return
        self.tree.selection_set("0")
        self.status.set(self.tr("wizard.online.choose_event", count=len(self.events)))
        self.action.configure(state="normal")

    def _load_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        event = self.events[int(selection[0])]
        self.action.configure(state="disabled")
        self.status.set(self.tr("wizard.online.loading_rosters", name=event.name))
        self._start(lambda: fetch_jump_rosters(event), lambda result, error: self._rosters_ready(event, result, error))

    def _rosters_ready(self, event: AtletikaEvent, result: object, error: Exception | None) -> None:
        if not self.winfo_exists():
            return
        if error:
            self.status.set(self.tr("wizard.online.offline"))
            self.action.configure(state="normal")
            return
        self.rosters = list(result or [])
        if not self.rosters:
            self.status.set(self.tr("wizard.online.no_long_jump"))
            self.action.configure(state="normal")
            return
        if len(self.rosters) == 1:
            self.on_import(event, self.rosters)
            self.destroy()
            return
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=("group", "name", "athletes"), selectmode="extended")
        for key, width in (("group", 100), ("name", 430), ("athletes", 100)):
            self.tree.heading(key, text=self.tr(f"wizard.online.{key}"))
            self.tree.column(key, width=width, minwidth=80, stretch=key == "name")
        for index, roster in enumerate(self.rosters):
            group = self.tr(f"wizard.groups.{roster.group.lower()}")
            self.tree.insert("", "end", iid=str(index), values=(group, roster.label, len(roster.athletes)))
        self.tree.selection_set(tuple(str(index) for index in range(len(self.rosters))))
        self.status.set(self.tr("wizard.online.choose_disciplines"))
        self.action.configure(text=self.tr("wizard.online.import_selected"), state="normal", command=lambda: self._import_selected(event))

    def _import_selected(self, event: AtletikaEvent) -> None:
        selected = [self.rosters[int(item)] for item in self.tree.selection()]
        if not selected:
            return
        self.on_import(event, selected)
        self.destroy()