from __future__ import annotations

from queue import Queue
import time

from src.attempts import AttemptManager
from src.config import AttemptsConfig, ExportConfig
from src.models import AttemptDecision
from src.ring_buffer import TimeRingBuffer


def fill_ring(ring, jpeg, count=10):
    start = time.monotonic_ns()
    for i in range(count):
        ring.append(start + i * 10_000_000, jpeg, 160, 90)


def test_decision_metadata_and_clear_all(tmp_path, jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(5, 128)
    fill_ring(ring, jpeg)
    (tmp_path / "cache").mkdir()
    manager = AttemptManager(ring, AttemptsConfig(pre_seconds=1, post_seconds=10), ExportConfig(), tmp_path / "cache", Queue())
    created = manager.create_attempt(competitor_group="Girls", competitor_number=4, competitor_attempt_number=2)
    assert created is not None
    assert manager.set_decision(created.attempt_id, AttemptDecision.FOUL)
    stored = manager.get_attempt(created.attempt_id)
    assert stored.decision is AttemptDecision.FOUL
    assert stored.roster_label == "Girls #4 · Try 2"
    metadata = tmp_path / "cache" / f"attempt_{created.attempt_id:04d}.session.json"
    assert metadata.exists()
    assert manager.clear_all() == 1
    assert manager.attempts() == []
    assert not list((tmp_path / "cache").glob("attempt_*.*"))
