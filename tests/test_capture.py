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


def test_capture_mode_emits_recordable_packets_without_filling_buffer():
    camera = CameraConfig(source_type='synthetic', width=160, height=90, fps=60)
    buffer_config = BufferConfig(duration_seconds=2, max_memory_mb=128, encoder_queue_size=64)
    ring = TimeRingBuffer(2, 128)
    packets = []
    engine = CaptureEngine(camera, buffer_config, ring, buffer_enabled=False)
    engine.set_packet_listener(packets.append)
    engine.start()
    time.sleep(.35)
    alive = engine.stop(timeout=2)
    assert alive == []
    assert packets
    assert len(ring) == 0
    assert packets[0].wall_time_ns > 0
