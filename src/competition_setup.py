from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal

from .config import AppConfig, CompetitionConfig


CompetitionTemplate = Literal["simple", "final", "judge_only"]
RecordingDisposition = Literal["keep", "clear"]
ReadinessLevel = Literal["ready", "warming", "warning"]


@dataclass(frozen=True, slots=True)
class WizardReadiness:
    language: str
    capture_running: bool
    captured_frames: int
    capture_fps: float
    requested_fps: float
    source_description: str
    last_error: str
    buffer_frame_count: int
    buffer_seconds: float
    cache_bytes: int
    cache_limit_bytes: int
    temporary_recording_count: int

    def issue_keys(self) -> tuple[str, ...]:
        issues: list[str] = []
        established = self.captured_frames > 20
        source_failed = bool(self.last_error.strip()) or any(
            token in self.source_description.lower() for token in ("disconnected", "reconnecting")
        )
        if not self.capture_running or source_failed or (established and self.capture_fps <= 0):
            issues.append("no_video")
        elif established and self.requested_fps > 0 and self.capture_fps < self.requested_fps * .85:
            issues.append("low_fps")
        if established and self.buffer_frame_count <= 0:
            issues.append("empty_buffer")
        if self.cache_limit_bytes > 0 and self.cache_bytes >= self.cache_limit_bytes * .8:
            issues.append("cache_high")
        return tuple(issues)

    @property
    def level(self) -> ReadinessLevel:
        if self.issue_keys():
            return "warning"
        if self.captured_frames <= 20 or self.buffer_frame_count <= 0:
            return "warming"
        return "ready"


class CompetitionSetupModel:
    """Pure competition-only draft used by the setup wizard."""

    def __init__(self, config: CompetitionConfig) -> None:
        self.competition = deepcopy(config)
        self.template: CompetitionTemplate = self._infer_template()
        self.normalize_dependencies()

    def _infer_template(self) -> CompetitionTemplate:
        if not self.competition.enabled:
            return "judge_only"
        return "final" if self.competition.final_round_enabled else "simple"

    def apply_template(self, template: CompetitionTemplate) -> None:
        if template not in {"simple", "final", "judge_only"}:
            raise ValueError(f"Unsupported competition template: {template}")
        self.template = template
        c = self.competition
        if template == "judge_only":
            c.enabled = False
            # Judge-only replay is intentionally a review surface, not a
            # competition station: remove verdict controls, roster/board
            # navigation, special results, and rotation-related behavior.
            c.decision_controls_enabled = False
            c.require_decision_before_continue = False
            c.auto_advance_on_attempt_complete = False
            c.auto_advance_after_decision = False
            c.show_competitor_selector = False
            c.show_competition_board = False
            c.show_state_banner = False
            c.next_athlete_overlay = False
            c.enable_special_results = False
            c.keyboard_competition_controls = False
            return
        c.enabled = True
        c.default_attempts_per_competitor = 3
        c.require_decision_before_continue = False
        c.next_athlete_overlay = True
        c.show_state_banner = True
        c.final_round_enabled = template == "final"
        if template == "final":
            c.finalists_count = 8
            c.final_attempts = 3
            c.final_order = "reverse"
        for enabled_name, count_name in (("boys_enabled", "boys_competitors"), ("girls_enabled", "girls_competitors")):
            if getattr(c, enabled_name) and getattr(c, count_name) <= 0:
                setattr(c, count_name, 8)
        self.normalize_dependencies()

    def normalize_dependencies(self) -> None:
        c = self.competition
        if c.active_group == "Boys" and not c.boys_enabled and c.girls_enabled:
            c.active_group = "Girls"
        elif c.active_group == "Girls" and not c.girls_enabled and c.boys_enabled:
            c.active_group = "Boys"

    def validate_step(self, step: str) -> dict[str, str]:
        c = self.competition
        errors: dict[str, str] = {}
        if step in {"groups", "review"} and c.enabled:
            if not c.boys_enabled and not c.girls_enabled:
                errors["groups"] = "group_required"
            if c.boys_enabled and not 1 <= c.boys_competitors <= 200:
                errors["boys_count"] = "athlete_count"
            if c.girls_enabled and not 1 <= c.girls_competitors <= 200:
                errors["girls_count"] = "athlete_count"
        if step in {"attempts", "review"} and c.enabled:
            if not 1 <= c.default_attempts_per_competitor <= 20:
                errors["qualification"] = "attempt_count"
            if c.final_round_enabled:
                if not 1 <= c.final_attempts <= 20:
                    errors["final_attempts"] = "attempt_count"
                if not 1 <= c.finalists_count <= 200:
                    errors["finalists"] = "finalist_count"
                enabled_counts = [
                    count for enabled, count in (
                        (c.boys_enabled, c.boys_competitors),
                        (c.girls_enabled, c.girls_competitors),
                    ) if enabled and count > 0
                ]
                if enabled_counts and c.finalists_count > min(enabled_counts):
                    errors["finalists"] = "finalists_exceed_group"
                if c.final_order not in {"same", "reverse", "manual"}:
                    errors["final_order"] = "final_order"
        return errors

    def expected_attempt_cells(self) -> int:
        c = self.competition
        if not c.enabled:
            return 0
        groups = int(c.boys_enabled) + int(c.girls_enabled)
        qualification = (
            (c.boys_competitors if c.boys_enabled else 0)
            + (c.girls_competitors if c.girls_enabled else 0)
        ) * c.default_attempts_per_competitor
        final = groups * c.finalists_count * c.final_attempts if c.final_round_enabled else 0
        return qualification + final

    def build_config(self) -> CompetitionConfig:
        self.normalize_dependencies()
        errors = self.validate_step("review")
        if errors:
            raise ValueError(next(iter(errors.values())))
        return deepcopy(self.competition)


def merge_competition_setup(current: AppConfig, competition: CompetitionConfig) -> AppConfig:
    """Merge a wizard result without reverting settings changed while it was open."""
    merged = deepcopy(current)
    merged.competition = deepcopy(competition)
    merged.competition.current_competitor_by_group = {"Boys": 1, "Girls": 1}
    merged.competition.finalist_numbers_by_group = {"Boys": [], "Girls": []}
    merged.competition.final_round_started_by_group = {"Boys": False, "Girls": False}
    return merged
