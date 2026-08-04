from __future__ import annotations

import time
import tkinter as tk

from src.competition_board import CompetitionBoard
from src.config import CompetitionConfig
from src.models import AttemptDecision, AttemptSession
from src.theme import DARK, LIGHT, ThemeManager


def _attempt(athlete: int, number: int, attempt_id: int, decision: AttemptDecision) -> AttemptSession:
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
        decision=decision,
    )


def test_every_board_cell_is_clickable_and_recordings_open_on_one_click():
    root = tk.Tk()
    ThemeManager(root).apply("dark")
    opened: list[int] = []
    selected: list[tuple[int, int]] = []
    marked: list[tuple[int, AttemptDecision]] = []
    marked_empty: list[tuple[int, int, AttemptDecision]] = []
    deleted: list[int] = []
    board = CompetitionBoard(
        root, DARK, opened.append, lambda athlete, attempt: selected.append((athlete, attempt)),
        lambda attempt_id, decision: marked.append((attempt_id, decision)),
        lambda athlete, attempt, decision: marked_empty.append((athlete, attempt, decision)), deleted.append,
    )
    board.pack(fill="both", expand=True)
    config = CompetitionConfig(
        boys_competitors=2,
        girls_enabled=False,
        default_attempts_per_competitor=2,
        final_round_enabled=True,
        final_attempts=1,
        finalist_numbers_by_group={"Boys": [1], "Girls": []},
    )
    recorded = [
        _attempt(1, 1, 101, AttemptDecision.NOT_DECIDED),
        _attempt(1, 2, 102, AttemptDecision.VALID),
        _attempt(2, 1, 201, AttemptDecision.FOUL),
        _attempt(2, 2, 202, AttemptDecision.REVIEW),
    ]
    board.set_data(config, "Boys", recorded, 1, 1)
    root.update()

    try:
        cells = {(athlete, attempt): (x0, y0, x1, y1) for x0, y0, x1, y1, athlete, attempt in board._cell_boxes}
        assert set(cells) == {(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)}
        for cell, (x0, y0, x1, y1) in cells.items():
            assert board._hit((x0 + x1) // 2, (y0 + y1) // 2) == cell

        for cell, attempt_id in [((1, 1), 101), ((1, 2), 102), ((2, 1), 201), ((2, 2), 202)]:
            x0, y0, x1, y1 = cells[cell]
            board.canvas.event_generate("<Button-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
            root.update()
            assert opened[-1] == attempt_id
            assert board._focused_cell == cell
        assert selected == []
        rectangle, base_fill = board._cell_items[(2, 2)]
        board._pulse_started -= 0.35
        board._animate_focus()
        assert board.canvas.itemcget(rectangle, "fill") != base_fill
        assert board.canvas.itemcget(rectangle, "outline") == DARK["accent_hover"]

        board.apply_palette(LIGHT)
        root.update()
        assert board._focused_cell == (2, 2)
        light_rectangle, _light_base = board._cell_items[(2, 2)]
        board._animate_focus()
        assert board.canvas.itemcget(light_rectangle, "outline") == LIGHT["accent_hover"]

        # Even a visually disabled cell emits its exact hit target; the session
        # layer remains responsible for enforcing competition eligibility.
        x0, y0, x1, y1 = cells[(2, 3)]
        board.canvas.event_generate("<Button-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
        root.update()
        assert opened == [101, 102, 201, 202]
        assert selected == [(2, 3)]
        assert board._focused_cell == (2, 3)

        board.focus_cell((1, 1))
        assert board.move_focus(1, 0) == "break"
        assert board._focused_cell == (1, 2)
        assert board.move_focus(0, 1) == "break"
        assert board._focused_cell == (2, 2)
        assert board.move_focus(-1, 0) == "break"
        assert board._focused_cell == (2, 1)
        board.activate_focused()
        assert opened[-1] == 201

        board._context_attempt_id = 202
        board._context_mark(AttemptDecision.PASSED)
        board._context_delete()
        assert marked == [(202, AttemptDecision.PASSED)]
        assert deleted == [202]
        assert board.context_menu.entrycget(board.context_menu.index("end"), "label")

        assert board._prepare_context_cell((1, 3))
        assert board._context_attempt_id is None
        assert board._context_cell == (1, 3)
        assert board.context_menu.entrycget(board._delete_menu_index, "state") == "disabled"
        board._context_mark(AttemptDecision.FOUL)
        board._context_delete()
        assert marked_empty == [(1, 3, AttemptDecision.FOUL)]
        assert deleted == [202]
    finally:
        root.destroy()
