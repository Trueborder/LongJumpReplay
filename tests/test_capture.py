import time

from src.capture import CaptureEngine
from src.config import BufferConfig, CameraConfig
from src.ring_buffer import TimeRingBuffer


def test_synthetic_capture_stops_cleanly():
    camera = CameraConfig(source_type='synthetic', width=320, height=180, fps=120)
    buffer_config = BufferConfig(duration_seconds=2, max_memory_mb=256, encoder_queue_size=64)
    ring = TimeRingBuffer(2, 256)
    engine = CaptureEngine(camera, buffer_config, ring)
    engine.start()
    time.sleep(1.1)
    alive = engine.stop(timeout=2)
    assert alive == []
    assert engine.stats().capture_fps > 90
    assert len(ring) > 50
