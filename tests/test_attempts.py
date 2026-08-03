import time
from pathlib import Path
from queue import Queue

from src.attempts import AttemptManager
from src.config import AttemptsConfig, ExportConfig
from src.models import AttemptState
from src.ring_buffer import TimeRingBuffer


def _wait_for(manager, attempt_id, states, timeout=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        attempt = manager.get_attempt(attempt_id)
        if attempt and attempt.state in states:
            return attempt
        time.sleep(.05)
    return manager.get_attempt(attempt_id)


def test_attempt_is_pinned_then_encoded_and_exported(tmp_path, jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(3, 256)
    base = time.monotonic_ns()
    for i in range(31):
        ring.append(base + i * 20_000_000, jpeg, 160, 90)
    config = AttemptsConfig(pre_seconds=.4, post_seconds=.2, retention_minutes=1, max_attempts=4, max_cache_gb=.2)
    manager = AttemptManager(ring, config, ExportConfig(), tmp_path / 'cache', Queue())
    manager.start()
    attempt = manager.create_attempt()
    assert attempt is not None
    assert attempt.state is AttemptState.COLLECTING
    pinned_first_timestamp = attempt.start_timestamp_ns

    # Advance the rolling buffer beyond post-roll. The copied pre-roll survives.
    for i in range(31, 50):
        ring.append(base + i * 20_000_000, jpeg, 160, 90)
        time.sleep(.002)
    ready = _wait_for(manager, attempt.attempt_id, {AttemptState.READY, AttemptState.ERROR})
    assert ready and ready.state is AttemptState.READY, ready.error if ready else 'missing'
    assert ready.start_timestamp_ns == pinned_first_timestamp
    assert ready.temp_video_path and ready.temp_video_path.exists()
    media = manager.get_frame(ready.attempt_id, ready.freeze_frame_index)
    assert media.frame_bgr is not None

    exports = tmp_path / 'exports'
    assert manager.request_export(ready.attempt_id, exports)
    exported = _wait_for(manager, ready.attempt_id, {AttemptState.EXPORTED, AttemptState.ERROR})
    assert exported and exported.state is AttemptState.EXPORTED
    assert exported.export_path and exported.export_path.exists()
    manager.stop()


def test_selected_attempt_does_not_expire(tmp_path, jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(2, 128)
    base = time.monotonic_ns()
    for i in range(10): ring.append(base + i * 10_000_000, jpeg, 160, 90)
    config = AttemptsConfig(pre_seconds=.1, post_seconds=0, retention_minutes=.5)
    manager = AttemptManager(ring, config, ExportConfig(), tmp_path / 'cache', Queue())
    manager.start()
    attempt = manager.create_attempt()
    assert attempt and manager.selected_attempt().attempt_id == attempt.attempt_id
    manager.clear_selection()
    assert manager.selected_attempt() is None
    manager.stop()


def test_ready_attempt_is_recovered_from_temporary_cache(tmp_path, jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(2, 128)
    base = time.monotonic_ns()
    for i in range(24):
        ring.append(base + i * 20_000_000, jpeg, 160, 90)
    config = AttemptsConfig(pre_seconds=.2, post_seconds=0, retention_minutes=2)
    cache = tmp_path / 'cache'
    manager = AttemptManager(ring, config, ExportConfig(), cache, Queue())
    manager.start()
    created = manager.create_attempt()
    assert created
    ready = _wait_for(manager, created.attempt_id, {AttemptState.READY, AttemptState.ERROR})
    assert ready and ready.state is AttemptState.READY
    manager.stop()

    recovered_manager = AttemptManager(ring, config, ExportConfig(), cache, Queue())
    recovered_manager.start()
    recovered = recovered_manager.get_attempt(created.attempt_id)
    assert recovered and recovered.state is AttemptState.READY
    assert recovered.temp_video_path and recovered.temp_video_path.exists()
    assert recovered_manager.get_frame(recovered.attempt_id, recovered.freeze_frame_index).frame_bgr is not None
    recovered_manager.stop()
