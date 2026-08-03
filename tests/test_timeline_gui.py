import tkinter as tk

from src.models import TimelineModel
from src.theme import DARK
from src.timeline import ProfessionalTimeline, centered_window


def _model(playhead_ns: int) -> TimelineModel:
    second = 1_000_000_000
    return TimelineModel(
        start_ns=0,
        end_ns=30 * second,
        playhead_ns=playhead_ns,
        reference_ns=15 * second,
        freeze_ns=15 * second,
        markers_ns=(14 * second, 16 * second),
        available_start_ns=0,
        available_end_ns=30 * second,
        is_live=False,
    )


def test_centered_window_keeps_playhead_exactly_in_middle():
    start, end = centered_window(12_345_678_900, 2.0)
    assert (start + end) // 2 == 12_345_678_900
    assert end - start == 2_000_000_000


def test_timeline_reuses_canvas_items_and_fixed_playhead(tmp_path):
    root = tk.Tk()
    root.geometry("1000x180")
    timeline = ProfessionalTimeline(root, DARK, lambda _ts: None)
    timeline.pack(fill="both", expand=True)
    root.update()

    timeline.set_model(_model(15_000_000_000))
    root.update_idletasks()
    item_count = len(timeline.find_all())
    first_x = timeline.coords(timeline._items["fixed_playhead"])[0]

    for i in range(120):
        timeline.set_model(_model(15_000_000_000 + i * 8_333_333))
        root.update_idletasks()

    assert len(timeline.find_all()) == item_count
    second_x = timeline.coords(timeline._items["fixed_playhead"])[0]
    assert abs(first_x - second_x) < 0.01
    assert abs(second_x - timeline.winfo_width() / 2) < 0.01
    root.destroy()


def test_timeline_suspension_coalesces_many_updates():
    root = tk.Tk()
    root.geometry("900x180")
    timeline = ProfessionalTimeline(root, DARK, lambda _ts: None)
    timeline.pack(fill="both", expand=True)
    root.update()

    timeline.set_render_suspended(True)
    for i in range(100):
        timeline.set_model(_model(15_000_000_000 + i * 8_333_333))
    assert timeline._dirty_while_suspended
    assert not timeline._render_pending

    timeline.set_render_suspended(False)
    root.update_idletasks()
    assert not timeline._dirty_while_suspended
    assert not timeline._render_pending
    root.destroy()
