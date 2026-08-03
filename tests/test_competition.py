from __future__ import annotations

import time

from src.competition import CompetitionSession
from src.config import CompetitionConfig
from src.models import AttemptDecision, AttemptSession


def attempt(group: str, athlete: int, try_no: int, decision=AttemptDecision.PENDING) -> AttemptSession:
    return AttemptSession(
        attempt_id=athlete * 10 + try_no,
        created_monotonic_ns=0,
        created_wall_time=time.time(),
        freeze_timestamp_ns=1,
        pre_seconds=1,
        post_seconds=1,
        expires_at_wall_time=time.time() + 60,
        competitor_group=group,
        competitor_number=athlete,
        competitor_attempt_number=try_no,
        decision=decision,
    )


def test_roster_rotates_in_round_order():
    config = CompetitionConfig(boys_competitors=3, girls_enabled=False, default_attempts_per_competitor=2)
    session = CompetitionSession(config)
    assert session.assignment_for_current([]).competitor_number == 1
    attempts = [attempt("Boys", 1, 1, AttemptDecision.VALID)]
    next_assignment = session.advance(attempts)
    assert (next_assignment.competitor_number, next_assignment.attempt_number) == (2, 1)
    attempts += [attempt("Boys", 2, 1, AttemptDecision.FOUL)]
    next_assignment = session.advance(attempts)
    assert (next_assignment.competitor_number, next_assignment.attempt_number) == (3, 1)
    attempts += [attempt("Boys", 3, 1, AttemptDecision.REVIEW)]
    next_assignment = session.advance(attempts)
    assert (next_assignment.competitor_number, next_assignment.attempt_number) == (1, 2)


def test_individual_attempt_limits_and_completed_athlete():
    config = CompetitionConfig(
        boys_competitors=2,
        girls_enabled=False,
        default_attempts_per_competitor=3,
        attempts_overrides={"Boys:1": 1, "Boys:2": 4},
    )
    session = CompetitionSession(config)
    assert session.attempt_limit("Boys", 1) == 1
    assert session.attempt_limit("Boys", 2) == 4
    assert session.assignment_for_current([attempt("Boys", 1, 1)]) is None
    moved = session.advance([attempt("Boys", 1, 1)])
    assert (moved.competitor_number, moved.attempt_number) == (2, 1)


def test_competition_can_be_disabled():
    config = CompetitionConfig(enabled=False)
    session = CompetitionSession(config)
    assert session.assignment_for_current([]) is None
    assert session.advance([]) is None
