import json
import logging

from src.models import BufferStats, CaptureStats
from src.runtime_diagnostics import JsonLineFormatter, RuntimeTelemetry


def _capture() -> CaptureStats:
    return CaptureStats(120, 60, 120.0, 60.0, 0, 0, 0, 2.5, 0, "Synthetic", "")


def test_runtime_telemetry_reports_bounded_ui_latency():
    telemetry = RuntimeTelemetry(max_ui_samples=60)
    for value in (0.001, 0.002, 0.003, 0.150):
        telemetry.record_ui_tick(value)
    snapshot = telemetry.snapshot(_capture(), BufferStats(60, 1.0, 1024, 0, 59))
    assert snapshot.ui_average_ms == 39.0
    assert snapshot.ui_p95_ms == 150.0
    assert snapshot.ui_stalls_over_100ms == 1
    assert snapshot.capture["capture_fps"] == 120.0


def test_json_line_formatter_includes_structured_event_data():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello", (), None)
    record.event_data = {"event": "freeze", "attempt_id": 7}
    payload = json.loads(JsonLineFormatter().format(record))
    assert payload["event"] == "freeze"
    assert payload["attempt_id"] == 7
    assert payload["message"] == "hello"
