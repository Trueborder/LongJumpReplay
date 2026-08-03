"""Small GUI benchmark for the pooled fixed-playhead timeline.

Run from the project root. On Linux, use xvfb-run; on Windows run normally.
"""
from __future__ import annotations

import statistics
import time
import tkinter as tk

from src.models import TimelineModel
from src.theme import DARK
from src.timeline import ProfessionalTimeline


def run_once(iterations: int = 600) -> float:
    root = tk.Tk()
    root.geometry("1280x160")
    timeline = ProfessionalTimeline(root, DARK, lambda _timestamp: None)
    timeline.pack(fill="both", expand=True)
    root.update()
    second = 1_000_000_000
    started = time.perf_counter()
    for index in range(iterations):
        playhead = 15 * second + index * 8_333_333
        timeline.set_model(
            TimelineModel(
                0,
                30 * second,
                playhead,
                15 * second,
                15 * second,
                (14 * second, 16 * second),
                0,
                30 * second,
                False,
            )
        )
        root.update_idletasks()
    elapsed = time.perf_counter() - started
    root.destroy()
    return elapsed


if __name__ == "__main__":
    results = [run_once() for _ in range(3)]
    median = statistics.median(results)
    print("Timeline benchmark: 600 rendered model updates")
    print("Runs:", ", ".join(f"{value:.3f}s" for value in results))
    print(f"Median: {median:.3f}s ({median / 600 * 1000:.3f} ms/update)")
