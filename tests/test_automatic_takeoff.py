from __future__ import annotations

import time

import numpy as np

from src import automatic_takeoff as module
from src.automatic_takeoff import AdvisoryStatus, AutomaticTakeoffMonitor, analyse_attempt
from src.models import FramePacket
from src.takeoff_assist import TakeoffCandidate
from src.top_view_projection import FootEstimate, ProjectionCalibration, ProjectionMeasurement


def _packets(count: int = 5) -> list[FramePacket]:
    return [FramePacket(index, index * 40_000_000, b"jpeg", 100, 100) for index in range(count)]


def _calibration() -> ProjectionCalibration:
    return ProjectionCalibration(((0, 0), (1, 0), (1, 1), (0, 1)), ((0, .7), (1, .7)), pad_length_cm=120.1, pad_width_cm=34)


def _install_detection_stubs(monkeypatch, measurements: list[ProjectionMeasurement]) -> None:
    monkeypatch.setattr(module, "detect_takeoff_candidate", lambda *_args, **_kwargs: TakeoffCandidate(2, .96, 1.0, 0, 160_000_000, (1, 2, 3)))
    monkeypatch.setattr(module, "decode_packet", lambda _packet: np.zeros((100, 100, 3), np.uint8))
    monkeypatch.setattr(module, "estimate_foot_polygon", lambda *_args, **_kwargs: FootEstimate(((30, 40), (55, 40), (55, 60), (30, 60)), .95))
    values = iter(measurements)
    monkeypatch.setattr(module, "measure_projected_foot", lambda *_args, **_kwargs: next(values))


def _measurement(distance: float, uncertainty: float = .3, confidence: float = .95) -> ProjectionMeasurement:
    status = "clear" if distance > uncertainty else ("over" if distance < -uncertainty else "touching")
    return ProjectionMeasurement(((0, 0), (1, 0), (1, 1)), distance, uncertainty, status, (0, 0), (0, 0), confidence)


def test_temporal_consensus_can_advise_valid(monkeypatch) -> None:
    _install_detection_stubs(monkeypatch, [_measurement(2.0), _measurement(1.8), _measurement(2.2)])
    result = analyse_attempt(_packets(), 80_000_000, (.1, .1, .8, .8), _calibration())
    assert result.status is AdvisoryStatus.VALID
    assert result.confidence >= .82


def test_temporal_consensus_can_advise_foul(monkeypatch) -> None:
    _install_detection_stubs(monkeypatch, [_measurement(-1.5), _measurement(-1.2), _measurement(.1)])
    result = analyse_attempt(_packets(), 80_000_000, (.1, .1, .8, .8), _calibration())
    assert result.status is AdvisoryStatus.FOUL
    assert result.signed_clearance_cm is not None and result.signed_clearance_cm < 0


def test_uncertain_edge_is_review(monkeypatch) -> None:
    _install_detection_stubs(monkeypatch, [_measurement(.1), _measurement(-.1), _measurement(.2)])
    result = analyse_attempt(_packets(), 80_000_000, (.1, .1, .8, .8), _calibration())
    assert result.status is AdvisoryStatus.REVIEW


def test_missing_candidate_falls_back_to_target_frame(monkeypatch) -> None:
    monkeypatch.setattr(module, "detect_takeoff_candidate", lambda *_args, **_kwargs: None)
    packets = _packets(7)
    result = analyse_attempt(packets, packets[4].timestamp_ns, (.1, .1, .8, .8), _calibration())
    assert result.status is AdvisoryStatus.REVIEW
    assert result.frame_index == 4


def test_live_gate_metrics_are_quiet_without_change_and_active_near_line() -> None:
    previous = np.zeros((80, 120, 3), np.uint8)
    current = previous.copy()
    quiet, _ = AutomaticTakeoffMonitor._metrics(previous, current, ((60, 0), (60, 80)))
    current[30:55, 50:72] = 255
    active, proximity = AutomaticTakeoffMonitor._metrics(previous, current, ((60, 0), (60, 80)))
    assert quiet == 0
    assert active > .01
    assert proximity > .5


def test_live_gate_emits_for_short_strong_takeoff() -> None:
    events = []
    monitor = AutomaticTakeoffMonitor(events.append, width=120, sample_hz=30, cooldown_seconds=.5)
    monitor.start()
    try:
        base = np.zeros((80, 120, 3), np.uint8)
        timestamp = 0
        for _ in range(6):
            monitor.offer(base, timestamp, (0, 0, 1, 1), ((.5, 0), (.5, 1)), enabled=True)
            timestamp += 40_000_000
            time.sleep(.04)
        moving = base.copy()
        moving[25:60, 48:78] = 255
        monitor.offer(moving, timestamp, (0, 0, 1, 1), ((.5, 0), (.5, 1)), enabled=True)
        timestamp += 40_000_000
        time.sleep(.04)
        for _ in range(4):
            monitor.offer(moving, timestamp, (0, 0, 1, 1), ((.5, 0), (.5, 1)), enabled=True)
            timestamp += 40_000_000
            time.sleep(.04)
        deadline = time.monotonic() + .5
        while not events and time.monotonic() < deadline:
            time.sleep(.01)
        assert len(events) == 1
        assert events[0].confidence > .5
        assert events[0].timestamp_ns == 240_000_000
    finally:
        monitor.stop()
