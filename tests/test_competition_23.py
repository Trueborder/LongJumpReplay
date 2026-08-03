from __future__ import annotations

import time

from src.competition import CompetitionSession
from src.config import CompetitionConfig
from src.models import AttemptDecision, AttemptSession


def made(athlete: int, attempt_no: int, phase: str = "qualification") -> AttemptSession:
    return AttemptSession(
        attempt_id=athlete * 100 + attempt_no,
        created_monotonic_ns=0,
        created_wall_time=time.time(),
        freeze_timestamp_ns=1,
        pre_seconds=0,
        post_seconds=0,
        expires_at_wall_time=time.time() + 60,
        competitor_group="Boys",
        competitor_number=athlete,
        competitor_attempt_number=attempt_no,
        competition_phase=phase,
        decision=AttemptDecision.NOT_DECIDED,
        rotation_completed=True,
    )


def test_three_rounds_then_manual_finalists_receive_three_more_attempts():
    config = CompetitionConfig(
        boys_competitors=8,
        girls_enabled=False,
        default_attempts_per_competitor=3,
        final_round_enabled=True,
        finalists_count=4,
        final_attempts=3,
        final_order="same",
    )
    session = CompetitionSession(config)
    attempts = [made(athlete, attempt_no) for attempt_no in range(1, 4) for athlete in range(1, 9)]
    assert session.qualification_complete(attempts)
    assert session.set_finalists("Boys", [2, 4, 6, 8]) == [2, 4, 6, 8]
    assert session.start_final_round("Boys")
    pending = session.pending_assignments(attempts, "Boys")
    assert [(a.competitor_number, a.attempt_number) for a in pending[:4]] == [(2, 4), (4, 4), (6, 4), (8, 4)]
    assert [(a.competitor_number, a.attempt_number) for a in pending[-4:]] == [(2, 6), (4, 6), (6, 6), (8, 6)]
