from pathlib import Path

from src.models import BufferStats, CaptureStats
from src.performance_monitor import PerformanceMonitor


def _capture_stats() -> CaptureStats:
    return CaptureStats(
        captured_frames=240,
        encoded_frames=240,
        capture_fps=25.0,
        encode_fps=25.0,
        queue_drops=0,
        read_failures=0,
        encode_failures=0,
        average_encode_ms=2.0,
        queue_depth=0,
        source_description="Synthetic camera",
        last_error="",
    )


def _buffer_stats() -> BufferStats:
    return BufferStats(
        frame_count=120,
        duration_seconds=5.0,
        memory_bytes=1024 * 1024,
        oldest_seq=1,
        newest_seq=120,
    )


def test_paused_capture_sample_reports_zero_fps_and_app_ram(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.performance_monitor._memory_usage", lambda: (321.0, 70.0))
    monitor = PerformanceMonitor(tmp_path)

    sample = monitor.sample(
        _capture_stats(),
        _buffer_stats(),
        cache_bytes=0,
        ui_p95_ms=4.0,
        capture_active=False,
    )

    assert sample is not None
    assert sample.capture_fps == 0.0
    assert sample.encode_fps == 0.0
    assert sample.process_ram_mb == 321.0
