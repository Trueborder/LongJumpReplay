from __future__ import annotations

import time

from src.adjudication import AthleteContext
from src.announcer_helper import announcer_athlete_name
from src.competition import CompetitionSession, RosterAssignment
from src.config import AppConfig, CompetitionConfig, load_config, save_config
from src.i18n import Translator
from src.main_window import MainWindow
from src.models import AttemptDecision, AttemptSession


def _attempt(athlete: int, try_no: int) -> AttemptSession:
    return AttemptSession(
        attempt_id=athlete * 10 + try_no,
        created_monotonic_ns=0,
        created_wall_time=time.time(),
        freeze_timestamp_ns=1,
        pre_seconds=1,
        post_seconds=1,
        expires_at_wall_time=time.time() + 60,
        competitor_group="Boys",
        competitor_number=athlete,
        competitor_attempt_number=try_no,
        decision=AttemptDecision.VALID,
    )


def test_announcer_name_uses_uppercase_surname_and_number_fallback():
    assert announcer_athlete_name(
        AthleteContext("1", name="Jan Novák", competitor_number=1), "cs"
    ) == "NOVÁK"
    assert announcer_athlete_name(
        AthleteContext("2", name="Nový, Petr", competitor_number=2), "cs"
    ) == "NOVÝ"
    assert announcer_athlete_name(
        AthleteContext("12", competitor_number=12), "cs"
    ) == "ZÁVODNÍK #12"
    assert announcer_athlete_name(
        AthleteContext("12", competitor_number=12), "en"
    ) == "ATHLETE #12"


def test_following_assignment_uses_round_major_order():
    session = CompetitionSession(CompetitionConfig(
        boys_competitors=3, girls_enabled=False, default_attempts_per_competitor=2,
    ))
    assert session.following_assignment([], RosterAssignment("Boys", 1, 1)) == RosterAssignment("Boys", 2, 1)
    assert session.following_assignment([], RosterAssignment("Boys", 3, 1)) == RosterAssignment("Boys", 1, 2)


def test_following_assignment_wraps_to_an_earlier_skipped_cell():
    session = CompetitionSession(CompetitionConfig(
        boys_competitors=3, girls_enabled=False, default_attempts_per_competitor=1,
    ))
    attempts = [_attempt(2, 1)]
    assert session.following_assignment(attempts, RosterAssignment("Boys", 3, 1)) == RosterAssignment("Boys", 1, 1)


def test_following_assignment_is_none_for_the_last_remaining_athlete():
    session = CompetitionSession(CompetitionConfig(
        boys_competitors=3, girls_enabled=False, default_attempts_per_competitor=1,
    ))
    attempts = [_attempt(1, 1), _attempt(2, 1)]
    assert session.following_assignment(attempts, RosterAssignment("Boys", 3, 1)) is None


def test_following_assignment_respects_individual_attempt_limits():
    session = CompetitionSession(CompetitionConfig(
        boys_competitors=2,
        girls_enabled=False,
        default_attempts_per_competitor=3,
        attempts_overrides={"Boys:1": 1},
    ))
    attempts = [_attempt(1, 1), _attempt(2, 1)]
    assert session.following_assignment(
        attempts,
        RosterAssignment("Boys", 2, 1),
    ) == RosterAssignment("Boys", 2, 2)


def test_following_assignment_respects_final_order():
    session = CompetitionSession(CompetitionConfig(
        boys_competitors=2,
        girls_enabled=False,
        default_attempts_per_competitor=1,
        final_round_enabled=True,
        final_attempts=1,
        final_order="manual",
        finalist_numbers_by_group={"Boys": [2, 1], "Girls": []},
        final_round_started_by_group={"Boys": True, "Girls": False},
    ))
    attempts = [_attempt(1, 1), _attempt(2, 1)]
    assert session.following_assignment(
        attempts,
        RosterAssignment("Boys", 2, 2, "final"),
    ) == RosterAssignment("Boys", 1, 2, "final")


class _Value:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class _Roster:
    def athlete_for(self, group: str, number: int) -> AthleteContext:
        names = {1: "Jan Novák", 2: "Petr Nový", 3: "Adam Třetí"}
        return AthleteContext(str(number), group=group, competitor_number=number, name=names[number])


def test_frozen_assignment_stays_in_announcer_message():
    app = object.__new__(MainWindow)
    app.config = AppConfig()
    app.config.general.language = "cs"
    app.config.competition.boys_competitors = 3
    app.config.competition.girls_enabled = False
    app.competition = CompetitionSession(app.config.competition)
    app.adjudication = _Roster()
    app.translator = Translator("cs")
    app.announcer_text_var = _Value()
    app._announcer_frozen_assignment = RosterAssignment("Boys", 1, 1)

    app._refresh_announcer_helper([_attempt(1, 1)], RosterAssignment("Boys", 3, 1))

    assert app.announcer_text_var.value == "Skáče NOVÁK, připraví se NOVÝ."


def test_announcer_visibility_setting_round_trips(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig()
    config.display.show_announcer_helper = False
    save_config(config, path)

    restored = load_config(path)

    assert restored.display.show_announcer_helper is False
    assert AppConfig().display.show_announcer_helper is True
