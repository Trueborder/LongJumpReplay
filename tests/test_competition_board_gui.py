from __future__ import annotations

import time
import tkinter as tk

from src.competition_board import CompetitionBoard
from src.config import CompetitionConfig
from src.models import AttemptDecision, AttemptSession
from src.theme import DARK, ThemeManager


def _attempt(athlete: int, number: int, attempt_id: int) -> AttemptSession:
    return AttemptSession(
        attempt_id=attempt_id,
        created_monotonic_ns=0,
        created_wall_time=time.time(),
        freeze_timestamp_ns=1,
        pre_seconds=0,
        post_seconds=0,
        expires_at_wall_time=time.time() + 60,
        competitor_group="Boys",
        competitor_number=athlete,
        competitor_attempt_number=number,
        decision=AttemptDecision.VALID,
    )


def test_every_board_cell_is_clickable_and_recordings_open_on_one_click():
    root = tk.Tk()
    ThemeManager(root).apply("dark")
    opened: list[int] = []
    selected: list[tuple[int, int]] = []
    board = CompetitionBoard(root, DARK, opened.append, lambda athlete, attempt: selected.append((athlete, attempt)))
    board.pack(fill="both", expand=True)
    config = CompetitionConfig(
        boys_competitors=2,
        girls_enabled=False,
        default_attempts_per_competitor=2,
        final_round_enabled=True,
        final_attempts=1,
        finalist_numbers_by_group={"Boys": [1], "Girls": []},
    )
    board.set_data(config, "Boys", [_attempt(2, 1, 201)], 1, 1)
    root.update()

    try:
        cells = {(athlete, attempt): (x0, y0, x1, y1) for x0, y0, x1, y1, athlete, attempt in board._cell_boxes}
        assert set(cells) == {(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)}
        for cell, (x0, y0, x1, y1) in cells.items():
            assert board._hit((x0 + x1) // 2, (y0 + y1) // 2) == cell

        x0, y0, x1, y1 = cells[(2, 1)]
        board.canvas.event_generate("<Button-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        root.update()
        assert opened == [201]
        assert selected == []

        # Even a visually disabled cell emits its exact hit target; the session
        # layer remains responsible for enforcing competition eligibility.
        x0, y0, x1, y1 = cells[(2, 3)]
        board.canvas.event_generate("<Button-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        root.update()
        assert opened == [201]
        assert selected == [(2, 3)]
    finally:
        root.destroy()
