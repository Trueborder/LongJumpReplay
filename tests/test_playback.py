import time
from queue import Queue

from src.attempts import AttemptManager
from src.config import AttemptsConfig, ExportConfig
from src.playback import PlaybackController, PlaybackMode
from src.ring_buffer import TimeRingBuffer


def test_freeze_creates_attempt_and_live_clears_selection(tmp_path, jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(2, 128)
    base = time.monotonic_ns()
    for i in range(20): ring.append(base + i * 10_000_000, jpeg, 160, 90)
    manager = AttemptManager(ring, AttemptsConfig(pre_seconds=.1, post_seconds=0), ExportConfig(), tmp_path, Queue())
    manager.start()
    playback = PlaybackController(ring, manager)
    attempt_id = playback.freeze_to_new_attempt()
    assert attempt_id is not None
    assert playback.mode is PlaybackMode.ATTEMPT
    playback.go_live()
    assert playback.mode is PlaybackMode.LIVE
    assert manager.selected_attempt() is None
    manager.stop()
