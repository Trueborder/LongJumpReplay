from __future__ import annotations

import cv2
import numpy as np

from src.models import FramePacket
from src.takeoff_assist import detect_takeoff_candidate
import src.takeoff_assist as takeoff_assist_module


def packet(index: int, frame: np.ndarray, fps: float = 60.0) -> FramePacket:
    ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    assert ok
    return FramePacket(index, int(index / fps * 1e9), data.tobytes(), frame.shape[1], frame.shape[0])


def test_takeoff_assist_finds_local_motion_in_board_roi():
    frames = []
    for i in range(30):
        frame = np.full((180, 320, 3), 70, dtype=np.uint8)
        cv2.rectangle(frame, (110, 105), (215, 120), (205, 205, 205), -1)  # board
        if 12 <= i <= 16:
            x = 105 + (i - 12) * 18
            cv2.ellipse(frame, (x, 92), (24, 11), 0, 0, 360, (20, 20, 20), -1)  # shoe
        frames.append(packet(i, frame))
    candidate = detect_takeoff_candidate(
        frames,
        freeze_timestamp_ns=frames[22].timestamp_ns,
        roi=(.28, .36, .46, .36),
        before_seconds=.4,
        after_seconds=0,
        target_width=200,
    )
    assert candidate is not None
    assert 12 <= candidate.frame_index <= 17
    assert candidate.confidence > .1
    assert candidate.analysis_start_ns == frames[0].timestamp_ns
    assert candidate.analysis_end_ns == frames[22].timestamp_ns


def test_takeoff_assist_ignores_motion_outside_roi():
    frames = []
    for i in range(20):
        frame = np.full((120, 240, 3), 80, dtype=np.uint8)
        if 5 <= i <= 10:
            cv2.circle(frame, (20 + i * 5, 15), 10, (255, 255, 255), -1)
        frames.append(packet(i, frame, 30))
    candidate = detect_takeoff_candidate(frames, frames[-1].timestamp_ns, (.45, .45, .3, .3), 1.0, 0, 160)
    assert candidate is None or candidate.peak_score < 1.0


def test_takeoff_assist_prefers_the_shoe_over_a_large_moving_shadow():
    frames = []
    ground = (145, 170, 200)
    shadow = tuple(int(value * .70) for value in ground)
    for i in range(38):
        frame = np.full((180, 320, 3), ground, dtype=np.uint8)
        cv2.rectangle(frame, (85, 105), (245, 126), (215, 220, 225), -1)
        if 6 <= i <= 16:
            cv2.ellipse(frame, (75 + (i - 6) * 10, 91), (66, 27), 0, 0, 360, shadow, -1)
        if 22 <= i <= 26:
            x = 115 + (i - 22) * 17
            cv2.ellipse(frame, (x, 92), (27, 12), 0, 0, 360, (18, 24, 31), -1)
        frames.append(packet(i, frame))
    candidate = detect_takeoff_candidate(
        frames,
        freeze_timestamp_ns=frames[32].timestamp_ns,
        roi=(.15, .30, .70, .48),
        before_seconds=.6,
        after_seconds=0,
        target_width=220,
    )
    assert candidate is not None
    assert 22 <= candidate.frame_index <= 27


def test_long_takeoff_window_uses_coarse_then_exact_local_analysis(monkeypatch):
    frames = []
    for i in range(150):
        frame = np.full((120, 240, 3), 75, dtype=np.uint8)
        cv2.rectangle(frame, (75, 75), (190, 91), (205, 205, 205), -1)
        if 88 <= i <= 101:
            x = 82 + (i - 88) * 7
            cv2.ellipse(frame, (x, 65), (20, 9), 0, 0, 360, (18, 22, 28), -1)
        frames.append(packet(i, frame, 60.0))

    real_decode = takeoff_assist_module.decode_packet
    decoded = 0

    def counted_decode(value):
        nonlocal decoded
        decoded += 1
        return real_decode(value)

    monkeypatch.setattr(takeoff_assist_module, "decode_packet", counted_decode)
    candidate = detect_takeoff_candidate(
        frames,
        frames[-1].timestamp_ns,
        (.24, .34, .62, .48),
        before_seconds=3.0,
        after_seconds=0,
        target_width=128,
    )

    assert candidate is not None
    assert 86 <= candidate.frame_index <= 103
    assert decoded < 100
