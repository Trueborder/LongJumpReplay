from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Sequence

import cv2
import numpy as np

from .exporter import decode_packet
from .models import FramePacket
from .motion_segmentation import foreground_motion_mask


_LOGGER = logging.getLogger("long_jump_replay.takeoff_assist")


@dataclass(frozen=True, slots=True)
class TakeoffCandidate:
    frame_index: int
    confidence: float
    peak_score: float
    analysis_start_ns: int
    analysis_end_ns: int
    # Frame indices that contained the compact dark shoe signal used by the
    # assist.  The projection window can reuse this bounded shortlist instead
    # of decoding and re-scanning the whole attempt a second time.
    usable_frame_indices: tuple[int, ...] = ()

    def visible_frame_for_lead(self, lead_frames: int) -> int:
        """Apply an operator lead without leaving the visible-shoe shortlist."""
        visible = tuple(sorted(set((*self.usable_frame_indices, self.frame_index))))
        target = self.frame_index + int(lead_frames)
        return min(visible, key=lambda value: (abs(value - target), value))


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
    return cv2.GaussianBlur(crop, (5, 5), 0)


def _transition_score(previous: np.ndarray, current: np.ndarray) -> tuple[float, float]:
    """Return motion and compact-shoe presence for one reduced ROI pair."""
    mask, shadow_mask = foreground_motion_mask(current, [previous])
    if shadow_mask is not None and shadow_mask.shape == mask.shape:
        shadow_u8 = shadow_mask.astype(np.uint8) * 255 if shadow_mask.dtype == bool else shadow_mask
        mask = cv2.bitwise_and(mask, cv2.bitwise_not(shadow_u8))
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    previous_hsv = cv2.cvtColor(previous, cv2.COLOR_BGR2HSV)
    difference = cv2.absdiff(current_gray, previous_gray).astype(np.float32)
    active = difference[mask > 0]
    active_fraction = active.size / difference.size if active.size else 0.0
    score = float(active.mean() * active_fraction) if active.size else 0.0
    if active_fraction > 0.12:
        score *= 0.25

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = float(mask.shape[0] * mask.shape[1])
    background_level = float(np.median(current_gray))
    current_hsv = cv2.cvtColor(current, cv2.COLOR_BGR2HSV)
    background_saturation = float(np.median(current_hsv[:, :, 1]))
    presence = 0.0
    for contour in contours:
        contour_area = float(cv2.contourArea(contour))
        # A shoe can occupy a large share of a tightly calibrated board ROI,
        # especially with a nearby camera. Broad illumination changes have
        # already been removed above and are penalised through active_fraction.
        if contour_area < area * 0.003 or contour_area > area * 0.24:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        touches_top = y <= 1
        # The field camera can crop the approaching shoe at the top of the
        # image. Permit only that expected entry edge, with a confidence
        # penalty below; side/bottom clipping remains too ambiguous.
        if x <= 1 or x + w >= mask.shape[1] - 1 or y + h >= mask.shape[0] - 1:
            continue
        aspect = max(w, h) / max(1.0, float(min(w, h)))
        if aspect > 7.0 or min(w, h) < 3:
            # Foul strips, lane markings and thin compression edges are not a
            # visible shoe even when they have strong contrast.
            continue
        contour_mask = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, -1)
        contour_level = float(current_gray[contour_mask > 0].mean()) if np.any(contour_mask) else background_level
        previous_level = float(previous_gray[contour_mask > 0].mean()) if np.any(contour_mask) else contour_level
        contour_saturation = float(current_hsv[:, :, 1][contour_mask > 0].mean()) if np.any(contour_mask) else background_saturation
        previous_saturation = float(previous_hsv[:, :, 1][contour_mask > 0].mean()) if np.any(contour_mask) else contour_saturation
        dark_contrast = background_level - contour_level
        colour_contrast = abs(contour_saturation - background_saturation)
        if dark_contrast < 24.0 and colour_contrast < 34.0:
            continue
        # Absolute frame difference also marks the area where a shoe has just
        # disappeared. Require evidence gained in the current frame so exposed
        # track or a following shadow cannot masquerade as the shoe.
        darkening = previous_level - contour_level
        saturation_gain = contour_saturation - previous_saturation
        if darkening < 8.0 and saturation_gain < 14.0:
            continue
        compactness = min(1.0, contour_area / max(1.0, float(w * h)))
        relative_area = contour_area / area
        size_score = min(1.0, relative_area / .065)
        if relative_area > .16:
            size_score *= max(.25, 1.0 - (relative_area - .16) / .12)
        visibility_penalty = .68 if touches_top else 1.0
        presence = max(presence, size_score * (0.55 + 0.45 * compactness) * visibility_penalty)
    return score, float(presence)


def _select_peak(scores: list[float], presence_scores: list[float]) -> tuple[int, float, float] | None:
    if len(scores) < 3 or max(scores) <= 0:
        return None
    raw = np.asarray(scores, dtype=np.float32)
    smoothed = np.convolve(raw, np.asarray([0.2, 0.6, 0.2], dtype=np.float32), mode="same")
    presence = np.asarray(presence_scores, dtype=np.float32)
    # Motion often peaks when the shoe leaves the board ROI. That transition
    # belongs to the previous visible shoe, but its current frame can be empty.
    # Never select a frame unless the current image itself contains the compact
    # shoe signal; combine motion and completeness only among visible frames.
    visible = presence >= .08
    if not bool(np.any(visible)):
        return None
    combined = smoothed * (.52 + .48 * np.clip(presence, 0.0, 1.0))
    selectable = combined.copy()
    selectable[~visible] = -1.0
    peak_pos = int(np.argmax(selectable))
    peak_value = float(selectable[peak_pos])
    onset_candidates = [
        pos for pos in range(max(0, peak_pos - 4), peak_pos + 1)
        if bool(visible[pos])
        and float(selectable[pos]) >= peak_value * .72
        and float(presence[pos]) >= max(.10, float(presence[peak_pos]) * .68)
    ]
    if onset_candidates:
        peak_pos = onset_candidates[0]
    peak = float(selectable[peak_pos])
    baseline = float(np.median(combined))
    spread = float(np.percentile(combined, 90) - baseline)
    confidence = max(0.0, min(1.0, (peak - baseline) / max(1e-6, peak + spread)))
    return peak_pos, peak, confidence


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
    board ROI. Colour-preserving brightness changes are suppressed as shadows,
    global brightness changes are removed, and a small temporal smoothing
    reduces JPEG flicker.
    """
    started = time.perf_counter()
    if len(packets) < 4:
        return None
    start = freeze_timestamp_ns - int(max(0.1, before_seconds) * 1e9)
    end = freeze_timestamp_ns + int(max(0.0, after_seconds) * 1e9)
    indexed = [(i, p) for i, p in enumerate(packets) if start <= p.timestamp_ns <= end]
    if len(indexed) < 4:
        return None

    roi_cache: dict[int, np.ndarray] = {}

    def reduced(position: int) -> np.ndarray:
        cached = roi_cache.get(position)
        if cached is None:
            cached = _roi_pixels(decode_packet(indexed[position][1]), roi, target_width)
            roi_cache[position] = cached
        return cached

    def analyse(positions: Sequence[int]) -> tuple[list[float], list[float], list[int]]:
        scores: list[float] = []
        presence_scores: list[float] = []
        indices: list[int] = []
        previous = None
        for position in positions:
            current = reduced(position)
            if previous is not None and previous.shape == current.shape:
                score, presence = _transition_score(previous, current)
                scores.append(score)
                presence_scores.append(presence)
                indices.append(indexed[position][0])
            previous = current
        return scores, presence_scores, indices

    # Long 120-FPS windows are searched cheaply first, then the exact local
    # frames are inspected. This preserves final frame precision while avoiding
    # full analysis of every JPEG in the complete window.
    stride = 1 if len(indexed) <= 48 else min(3, max(2, int(round(len(indexed) / 55.0))))
    coarse_positions = list(range(0, len(indexed), stride))
    if coarse_positions[-1] != len(indexed) - 1:
        coarse_positions.append(len(indexed) - 1)
    coarse_scores, coarse_presence, coarse_indices = analyse(coarse_positions)
    coarse_peak = _select_peak(coarse_scores, coarse_presence)
    if coarse_peak is None:
        return None

    if stride > 1:
        coarse_frame_index = coarse_indices[coarse_peak[0]]
        coarse_source_position = min(range(len(indexed)), key=lambda pos: abs(indexed[pos][0] - coarse_frame_index))
        radius = max(8, stride * 4)
        first = max(0, coarse_source_position - radius - 1)
        last = min(len(indexed), coarse_source_position + radius + 1)
        scores, presence_scores, indices = analyse(range(first, last))
        selected = _select_peak(scores, presence_scores)
        if selected is None:
            scores, presence_scores, indices = coarse_scores, coarse_presence, coarse_indices
            selected = coarse_peak
    else:
        scores, presence_scores, indices = coarse_scores, coarse_presence, coarse_indices
        selected = coarse_peak

    peak_pos, peak, confidence = selected
    presence = np.asarray(presence_scores, dtype=np.float32)
    usable = [indices[position] for position, value in enumerate(presence) if float(value) >= 0.12]
    if not usable:
        usable = [indices[peak_pos]]
    # Keep the projection shortlist small and centred on the selected onset.
    # These are the same frames that passed Take-off Assist's compact-object
    # gate, so the projection loader does not need another full segmentation
    # pass before opening the frame chooser.
    usable = sorted(set(usable), key=lambda value: (abs(value - indices[peak_pos]), value))[:5]
    result = TakeoffCandidate(
        indices[peak_pos],
        confidence,
        peak,
        indexed[0][1].timestamp_ns,
        indexed[-1][1].timestamp_ns,
        tuple(sorted(usable)),
    )
    _LOGGER.info(
        "takeoff_analysis duration_ms=%.2f window_frames=%d decoded_frames=%d stride=%d candidate=%d confidence=%.3f",
        (time.perf_counter() - started) * 1000.0,
        len(indexed),
        len(roi_cache),
        stride,
        result.frame_index,
        result.confidence,
    )
    return result
