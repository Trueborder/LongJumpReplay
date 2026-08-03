from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np

from .exporter import decode_packet
from .models import FramePacket


@dataclass(frozen=True, slots=True)
class TakeoffCandidate:
    frame_index: int
    confidence: float
    peak_score: float


def _roi_pixels(frame: np.ndarray, roi: tuple[float, float, float, float], target_width: int) -> np.ndarray:
    h, w = frame.shape[:2]
    x, y, rw, rh = roi
    x0 = max(0, min(w - 1, int(round(x * w))))
    y0 = max(0, min(h - 1, int(round(y * h))))
    x1 = max(x0 + 1, min(w, int(round((x + rw) * w))))
    y1 = max(y0 + 1, min(h, int(round((y + rh) * h))))
    crop = frame[y0:y1, x0:x1]
    scale = min(1.0, target_width / max(1, crop.shape[1]))
    if scale < 1:
        crop = cv2.resize(crop, (max(8, int(crop.shape[1] * scale)), max(8, int(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def detect_takeoff_candidate(
    packets: Sequence[FramePacket],
    freeze_timestamp_ns: int,
    roi: tuple[float, float, float, float],
    before_seconds: float,
    after_seconds: float,
    target_width: int = 240,
) -> TakeoffCandidate | None:
    """Locate the strongest local shoe/leg motion near the board.

    This is deliberately an assist, not an automatic foul decision. For the
    intended fixed ground camera, perpendicular to the runway beside the board,
    the athlete's foot produces a short, strong local change inside a calibrated
    board ROI. Global brightness changes are suppressed by subtracting the median
    difference, and a small temporal smoothing reduces JPEG flicker.
    """
    if len(packets) < 4:
        return None
    start = freeze_timestamp_ns - int(max(0.1, before_seconds) * 1e9)
    end = freeze_timestamp_ns + int(max(0.0, after_seconds) * 1e9)
    indexed = [(i, p) for i, p in enumerate(packets) if start <= p.timestamp_ns <= end]
    if len(indexed) < 4:
        return None

    scores: list[float] = []
    indices: list[int] = []
    previous = None
    for original_index, packet in indexed:
        frame = decode_packet(packet)
        if frame is None:
            continue
        current = _roi_pixels(frame, roi, target_width)
        if previous is not None and previous.shape == current.shape:
            diff = cv2.absdiff(current, previous).astype(np.float32)
            # Remove broad illumination changes. What remains is local motion.
            diff -= float(np.median(diff))
            np.maximum(diff, 0, out=diff)
            threshold = max(7.0, float(np.percentile(diff, 82)))
            active = diff[diff >= threshold]
            score = float(active.mean() * (active.size / diff.size)) if active.size else 0.0
            scores.append(score)
            indices.append(original_index)
        previous = current

    if len(scores) < 3 or max(scores) <= 0:
        return None
    raw = np.asarray(scores, dtype=np.float32)
    smoothed = np.convolve(raw, np.asarray([0.2, 0.6, 0.2], dtype=np.float32), mode="same")
    peak_pos = int(np.argmax(smoothed))
    peak = float(smoothed[peak_pos])
    baseline = float(np.median(smoothed))
    spread = float(np.percentile(smoothed, 90) - baseline)
    confidence = max(0.0, min(1.0, (peak - baseline) / max(1e-6, peak + spread)))
    return TakeoffCandidate(indices[peak_pos], confidence, peak)
