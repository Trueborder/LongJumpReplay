import time
from pathlib import Path
from queue import Queue

import numpy as np

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
    events = Queue()
    manager = AttemptManager(ring, config, ExportConfig(), tmp_path / 'cache', events)
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
    progress = []
    while not events.empty():
        event, payload = events.get_nowait()
        if event == "attempt_export_progress":
            progress.append(payload)
    assert progress
    assert progress[0][1] == 0
    assert progress[-1][1] == progress[-1][2] == exported.export_path.stat().st_size
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


def test_in_progress_attempt_cannot_be_deleted(tmp_path, jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(2, 128)
    ring.append(time.monotonic_ns(), jpeg, 160, 90)
    manager = AttemptManager(ring, AttemptsConfig(pre_seconds=.1, post_seconds=.1), ExportConfig(), tmp_path / 'cache', Queue())
    created = manager.create_attempt()
    assert created is not None

    for state in (AttemptState.COLLECTING, AttemptState.ENCODING, AttemptState.EXPORTING):
        with manager._lock:
            manager._find_locked(created.attempt_id).state = state
        assert not manager.delete(created.attempt_id, force=True)
        assert manager.get_attempt(created.attempt_id) is not None


def test_encoded_frame_reader_reuses_sequential_decode_and_recent_frames(monkeypatch, tmp_path):
    class FakeCapture:
        instances = []

        def __init__(self, _path):
            self.position = 0
            self.set_calls = []
            self.read_calls = 0
            FakeCapture.instances.append(self)

        def isOpened(self):
            return True

        def set(self, _property, value):
            self.position = int(value)
            self.set_calls.append(self.position)
            return True

        def read(self):
            frame = np.full((4, 6, 3), self.position, dtype=np.uint8)
            self.position += 1
            self.read_calls += 1
            return True, frame

        def release(self):
            return None

    monkeypatch.setattr('src.attempts.cv2.VideoCapture', FakeCapture)
    ring = TimeRingBuffer(2, 128)
    cache = tmp_path / 'cache'
    cache.mkdir()
    video = cache / 'attempt_0001.mp4'
    video.write_bytes(b'fake')
    manager = AttemptManager(ring, AttemptsConfig(), ExportConfig(), cache, Queue())
    from src.models import AttemptSession, AttemptState
    attempt = AttemptSession(
        attempt_id=1,
        created_monotonic_ns=0,
        created_wall_time=time.time(),
        freeze_timestamp_ns=1,
        pre_seconds=0,
        post_seconds=0,
        expires_at_wall_time=time.time() + 60,
        state=AttemptState.READY,
        temp_video_path=video,
        frame_count=8,
        fps=60,
    )
    manager._attempts.append(attempt)

    first = manager.get_frame(1, 0)
    second = manager.get_frame(1, 1)
    cached_first = manager.get_frame(1, 0)
    cached_second = manager.get_frame(1, 1)

    capture = FakeCapture.instances[0]
    assert capture.set_calls == [0]
    assert capture.read_calls == 2
    assert first.frame_bgr is cached_first.frame_bgr
    assert second.frame_bgr is cached_second.frame_bgr


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


def test_stalled_capture_finalizes_partial_post_roll(monkeypatch, tmp_path, jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(2, 128)
    base = 5_000_000_000
    ring.append(base, jpeg, 160, 90)
    config = AttemptsConfig(pre_seconds=.1, post_seconds=2, retention_minutes=1)
    manager = AttemptManager(ring, config, ExportConfig(), tmp_path / 'cache', Queue())
    now = [10_000_000_000]
    monkeypatch.setattr('src.attempts.time.monotonic_ns', lambda: now[0])
    attempt = manager.create_attempt()
    assert attempt and attempt.state is AttemptState.COLLECTING
    submitted = []
    monkeypatch.setattr(manager, '_submit_encode', submitted.append)
    now[0] += int((config.post_seconds + manager.POST_ROLL_STALL_GRACE_SECONDS + .1) * 1e9)
    manager._collect_post_roll()
    stalled = manager.get_attempt(attempt.attempt_id)
    assert stalled and stalled.state is AttemptState.ENCODING
    assert 'Post-roll ended early' in stalled.quality_warning
    assert submitted == [attempt.attempt_id]
