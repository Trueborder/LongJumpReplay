from __future__ import annotations

import cv2
import numpy as np

from src.models import FramePacket
from src.takeoff_assist import detect_takeoff_candidate


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


def test_takeoff_assist_ignores_motion_outside_roi():
    frames = []
    for i in range(20):
        frame = np.full((120, 240, 3), 80, dtype=np.uint8)
        if 5 <= i <= 10:
            cv2.circle(frame, (20 + i * 5, 15), 10, (255, 255, 255), -1)
        frames.append(packet(i, frame, 30))
    candidate = detect_takeoff_candidate(frames, frames[-1].timestamp_ns, (.45, .45, .3, .3), 1.0, 0, 160)
    assert candidate is None or candidate.peak_score < 1.0
