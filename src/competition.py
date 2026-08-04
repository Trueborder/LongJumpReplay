from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import CompetitionConfig
from .models import AttemptDecision, AttemptSession


@dataclass(frozen=True, slots=True)
class RosterAssignment:
    group: str
    competitor_number: int
    attempt_number: int
    phase: str = "qualification"


class CompetitionSession:
    """Deterministic round-based athlete rotation.

    The session deliberately treats recording completion separately from a
    decision. An attempt can therefore count in the running order while still
    being labelled Not decided and reviewed later.
    """

    GROUPS = ("Boys", "Girls")

    def __init__(self, config: CompetitionConfig) -> None:
        self.config = config
        self._selected_assignment: RosterAssignment | None = None
        self._normalise_current()

    def update_config(self, config: CompetitionConfig) -> None:
        self.config = config
        self._selected_assignment = None
        self._normalise_current()

    def enabled_groups(self) -> list[str]:
        groups: list[str] = []
        if self.config.boys_enabled and self.config.boys_competitors > 0:
            groups.append("Boys")
        if self.config.girls_enabled and self.config.girls_competitors > 0:
            groups.append("Girls")
        return groups

    def competitor_count(self, group: str) -> int:
        return self.config.boys_competitors if group == "Boys" else self.config.girls_competitors

    def qualification_limit(self, group: str, competitor_number: int) -> int:
        return int(self.config.attempts_overrides.get(f"{group}:{competitor_number}", self.config.default_attempts_per_competitor))

    def attempt_limit(self, group: str, competitor_number: int) -> int:
        base = self.qualification_limit(group, competitor_number)
        if self.final_started(group) and self.is_finalist(group, competitor_number):
            return base + self.config.final_attempts
        return base

    def current_group(self) -> str:
        groups = self.enabled_groups()
        if not groups:
            return "Boys"
        if self.config.active_group not in groups:
            self.config.active_group = groups[0]
        return self.config.active_group

    def current_competitor(self) -> int:
        group = self.current_group()
        count = max(1, self.competitor_count(group))
        value = int(self.config.current_competitor_by_group.get(group, 1))
        value = max(1, min(count, value))
        self.config.current_competitor_by_group[group] = value
        return value

    def set_current(self, group: str, competitor_number: int) -> None:
        if group not in self.GROUPS:
            raise ValueError("Unknown competition group")
        count = self.competitor_count(group)
        if count <= 0:
            raise ValueError(f"{group} has no configured competitors")
        self.config.active_group = group
        self.config.current_competitor_by_group[group] = max(1, min(count, int(competitor_number)))
        self._selected_assignment = None

    def select_attempt_cell(self, group: str, competitor_number: int, attempt_number: int) -> RosterAssignment | None:
        """Select an exact empty board cell as the next recording target."""
        if not self.config.enabled or group not in self.enabled_groups():
            return None
        number = int(competitor_number)
        attempt = int(attempt_number)
        if not 1 <= number <= self.competitor_count(group):
            return None
        base = self.qualification_limit(group, number)
        if self.final_started(group):
            if not self.is_finalist(group, number) or not base < attempt <= base + self.config.final_attempts:
                return None
            phase = "final"
        else:
            if not 1 <= attempt <= base:
                return None
            phase = "qualification"
        self.set_current(group, number)
        self._selected_assignment = RosterAssignment(group, number, attempt, phase)
        return self._selected_assignment

    def final_started(self, group: str) -> bool:
        return bool(self.config.final_round_started_by_group.get(group, False))

    def finalists(self, group: str) -> list[int]:
        count = self.competitor_count(group)
        raw = [int(v) for v in self.config.finalist_numbers_by_group.get(group, [])]
        values = [v for v in raw if 1 <= v <= count]
        if self.config.final_order == "reverse":
            values = list(reversed(values))
        return values

    def is_finalist(self, group: str, number: int) -> bool:
        return number in set(self.config.finalist_numbers_by_group.get(group, []))

    def set_finalists(self, group: str, numbers: Iterable[int]) -> list[int]:
        count = self.competitor_count(group)
        unique: list[int] = []
        for value in numbers:
            number = int(value)
            if 1 <= number <= count and number not in unique:
                unique.append(number)
        unique = unique[: self.config.finalists_count]
        self.config.finalist_numbers_by_group[group] = unique
        return unique

    def start_final_round(self, group: str) -> bool:
        if not self.config.final_round_enabled or not self.config.finalist_numbers_by_group.get(group):
            return False
        self.config.final_round_started_by_group[group] = True
        order = self.finalists(group)
        if order:
            self.set_current(group, order[0])
        return True

    @staticmethod
    def _counts(attempt: AttemptSession) -> bool:
        return attempt.counts_for_rotation and attempt.decision is not AttemptDecision.REATTEMPT

    def used_attempt_numbers(self, attempts: Iterable[AttemptSession], group: str, number: int) -> set[int]:
        return {
            a.competitor_attempt_number
            for a in attempts
            if a.competitor_group == group
            and a.competitor_number == number
            and a.competitor_attempt_number > 0
            and self._counts(a)
        }

    def assignment_for_current(self, attempts: Iterable[AttemptSession]) -> RosterAssignment | None:
        if not self.config.enabled:
            return None
        attempts_list = list(attempts)
        group = self.current_group()
        number = self.current_competitor()
        selected = self._selected_assignment
        if selected is not None:
            if selected.group == group and selected.competitor_number == number and selected.attempt_number not in self.used_attempt_numbers(attempts_list, group, number):
                return selected
            self._selected_assignment = None
        if self.final_started(group) and not self.is_finalist(group, number):
            return None
        used = self.used_attempt_numbers(attempts_list, group, number)
        base = self.qualification_limit(group, number)
        if self.final_started(group):
            start, end, phase = base + 1, base + self.config.final_attempts, "final"
        else:
            start, end, phase = 1, base, "qualification"
        next_try = next((i for i in range(start, end + 1) if i not in used), None)
        if next_try is None:
            return None
        return RosterAssignment(group, number, next_try, phase)

    def pending_assignments(self, attempts: Iterable[AttemptSession], group: str | None = None) -> list[RosterAssignment]:
        if not self.config.enabled:
            return []
        attempts_list = list(attempts)
        group = group or self.current_group()
        if self.final_started(group):
            athletes = self.finalists(group)
            phase = "final"
            rows: list[RosterAssignment] = []
            for offset in range(1, self.config.final_attempts + 1):
                for number in athletes:
                    attempt_no = self.qualification_limit(group, number) + offset
                    if attempt_no not in self.used_attempt_numbers(attempts_list, group, number):
                        rows.append(RosterAssignment(group, number, attempt_no, phase))
            return rows
        rows = []
        max_rounds = max((self.qualification_limit(group, n) for n in range(1, self.competitor_count(group) + 1)), default=0)
        for attempt_no in range(1, max_rounds + 1):
            for number in range(1, self.competitor_count(group) + 1):
                if attempt_no > self.qualification_limit(group, number):
                    continue
                if attempt_no not in self.used_attempt_numbers(attempts_list, group, number):
                    rows.append(RosterAssignment(group, number, attempt_no, "qualification"))
        return rows

    def next_assignment_after(self, attempts: Iterable[AttemptSession], completed: RosterAssignment) -> RosterAssignment | None:
        """Return the next pending cell in round-major board order without changing state."""
        pending = self.pending_assignments(attempts, completed.group)
        if not pending:
            return None
        order = self.finalists(completed.group) if self.final_started(completed.group) else list(range(1, self.competitor_count(completed.group) + 1))
        positions = {number: index for index, number in enumerate(order)}

        def rotation_key(assignment: RosterAssignment) -> tuple[int, int]:
            round_number = assignment.attempt_number
            if assignment.phase == "final":
                round_number -= self.qualification_limit(assignment.group, assignment.competitor_number)
            return round_number, positions.get(assignment.competitor_number, -1)

        completed_key = rotation_key(completed)
        return next((assignment for assignment in pending if rotation_key(assignment) > completed_key), pending[0])

    def advance(self, attempts: Iterable[AttemptSession]) -> RosterAssignment | None:
        if not self.config.enabled:
            return None
        attempts_list = list(attempts)
        group = self.current_group()
        pending = self.pending_assignments(attempts_list, group)
        if not pending:
            return None
        current = self.current_competitor()
        used_current = self.used_attempt_numbers(attempts_list, group, current)
        current_try = max(used_current, default=0)
        order = self.finalists(group) if self.final_started(group) else list(range(1, self.competitor_count(group) + 1))
        pos = {number: index for index, number in enumerate(order)}
        current_key = (current_try, pos.get(current, -1))
        target = next((a for a in pending if (a.attempt_number, pos.get(a.competitor_number, -1)) > current_key), pending[0])
        self.set_current(group, target.competitor_number)
        return target

    def qualification_complete(self, attempts: Iterable[AttemptSession], group: str | None = None) -> bool:
        group = group or self.current_group()
        if self.final_started(group):
            return True
        attempts_list = list(attempts)
        for number in range(1, self.competitor_count(group) + 1):
            used = self.used_attempt_numbers(attempts_list, group, number)
            if any(i not in used for i in range(1, self.qualification_limit(group, number) + 1)):
                return False
        return self.competitor_count(group) > 0

    def final_complete(self, attempts: Iterable[AttemptSession], group: str | None = None) -> bool:
        group = group or self.current_group()
        if not self.final_started(group):
            return False
        return not self.pending_assignments(attempts, group)

    def status_matrix(self, attempts: Iterable[AttemptSession], group: str | None = None) -> list[tuple[int, list[AttemptDecision | None]]]:
        group = group or self.current_group()
        attempts_list = list(attempts)
        total_columns = self.config.default_attempts_per_competitor + (self.config.final_attempts if self.config.final_round_enabled else 0)
        by_key = {
            (a.competitor_number, a.competitor_attempt_number): a.decision
            for a in attempts_list
            if a.competitor_group == group and a.competitor_attempt_number > 0 and self._counts(a)
        }
        rows: list[tuple[int, list[AttemptDecision | None]]] = []
        for number in range(1, self.competitor_count(group) + 1):
            qualification = self.qualification_limit(group, number)
            values: list[AttemptDecision | None] = []
            for attempt_no in range(1, total_columns + 1):
                if attempt_no > qualification and not self.is_finalist(group, number):
                    values.append(None)
                else:
                    values.append(by_key.get((number, attempt_no), AttemptDecision.NOT_DECIDED if attempt_no in self.used_attempt_numbers(attempts_list, group, number) else None))
            rows.append((number, values))
        return rows

    def _normalise_current(self) -> None:
        groups = self.enabled_groups()
        if groups and self.config.active_group not in groups:
            self.config.active_group = groups[0]
        for group in self.GROUPS:
            count = max(1, self.competitor_count(group))
            value = int(self.config.current_competitor_by_group.get(group, 1))
            self.config.current_competitor_by_group[group] = max(1, min(count, value))
