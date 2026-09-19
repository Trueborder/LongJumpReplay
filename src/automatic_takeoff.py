from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from queue import Empty, Full, Queue
from threading import Event, Thread
import logging
import math
import time
from typing import Callable, Sequence

import cv2
import numpy as np

from .exporter import decode_packet
from .models import FramePacket
from .takeoff_assist import TakeoffCandidate, detect_takeoff_candidate
from .top_view_projection import ProjectionCalibration, estimate_foot_polygon, measure_projected_foot


_LOGGER = logging.getLogger("long_jump_replay.automatic_takeoff")


class MonitorState(str, Enum):
    DISARMED = "disarmed"
    ARMING = "arming"
    ARMED = "armed"
    APPROACH = "approach"
    COOLDOWN = "cooldown"


class AdvisoryStatus(str, Enum):
    VALID = "valid"
    FOUL = "foul"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class TakeoffEvent:
    timestamp_ns: int
    confidence: float


@dataclass(frozen=True, slots=True)
class AutomaticAdvisory:
    status: AdvisoryStatus
    confidence: float
    frame_index: int
    signed_clearance_cm: float | None
    uncertainty_cm: float | None
    reason: str
    elapsed_ms: float
    engine: str = "temporal-classical-v1"


def shoe_foul_area_overlap(
    shoe_polygon_px: Sequence[Sequence[float]],
    foul_area: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
) -> tuple[float, float]:
    """Return overlap area and shoe-area ratio for the saved foul polygon.

    The calibration points are intentionally treated as an unordered convex
    area. This keeps judging independent from the order in which the four
    handles were placed in the startup wizard.
    """
    if len(shoe_polygon_px) < 3 or len(foul_area) != 4:
        return 0.0, 0.0
    width, height = frame_size
    if width < 2 or height < 2:
        return 0.0, 0.0
    shoe = cv2.convexHull(np.asarray(shoe_polygon_px, np.float32).reshape(-1, 1, 2))
    area = np.asarray(
        [(float(x) * width, float(y) * height) for x, y in foul_area],
        np.float32,
    ).reshape(-1, 1, 2)
    area = cv2.convexHull(area)
    shoe_area = float(cv2.contourArea(shoe))
    foul_area_px = float(cv2.contourArea(area))
    if shoe_area <= 1.0 or foul_area_px <= 1.0:
        return 0.0, 0.0
    overlap, _polygon = cv2.intersectConvexConvex(shoe, area)
    overlap = max(0.0, float(overlap))
    return overlap, overlap / shoe_area


@dataclass(frozen=True, slots=True)
class _Sample:
    timestamp_ns: int
    roi_bgr: np.ndarray
    line: tuple[tuple[float, float], tuple[float, float]] | None


class AutomaticTakeoffMonitor:
    """Bounded, low-resolution live event gate.

    The monitor only identifies a likely take-off instant. It never classifies
    a jump and never touches the capture thread. The latest reduced ROI replaces
    an older queued sample when a slow CPU falls behind.
    """

    def __init__(self, callback: Callable[[TakeoffEvent], None], *, width: int = 192,
                 sample_hz: float = 24.0, cooldown_seconds: float = 1.5,
                 warning_callback: Callable[[str], None] | None = None) -> None:
        self.callback = callback
        self.warning_callback = warning_callback
        self.width = max(96, min(320, int(width)))
        self.sample_period = 1.0 / max(4.0, min(30.0, float(sample_hz)))
        self.cooldown_seconds = max(.5, float(cooldown_seconds))
        self._queue: Queue[_Sample] = Queue(maxsize=1)
        self._stop = Event()
        self._thread = Thread(target=self._loop, name="automatic-takeoff-gate", daemon=True)
        self._last_offer = 0.0
        self._enabled = False
        self.state = MonitorState.DISARMED
        self._previous: np.ndarray | None = None
        self._still_frames = 0
        self._active_frames = 0
        self._quiet_after_active = 0
        self._peak: tuple[float, int] = (0.0, 0)
        self._first_active_timestamp_ns = 0
        self._cooldown_until = 0.0
        self._last_drift_warning = 0.0
        self.last_motion = 0.0
        self.last_proximity = 0.0

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, timeout: float = 1.0) -> list[str]:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(max(0.0, timeout))
        return [self._thread.name] if self._thread.is_alive() else []

    def reset(self) -> None:
        self._enabled = False
        self.state = MonitorState.DISARMED
        self._previous = None
        self._still_frames = self._active_frames = self._quiet_after_active = 0
        self._peak = (0.0, 0)
        self._first_active_timestamp_ns = 0
        self.last_motion = 0.0
        self.last_proximity = 0.0

    def offer(self, frame: np.ndarray, timestamp_ns: int, roi: Sequence[float],
              foul_line: Sequence[Sequence[float]] | None, *, enabled: bool) -> None:
        if not enabled or frame is None or frame.ndim != 3:
            if self._enabled:
                self.reset()
            return
        self._enabled = True
        now = time.perf_counter()
        if now - self._last_offer < self.sample_period:
            return
        self._last_offer = now
        h, w = frame.shape[:2]
        x, y, rw, rh = (float(value) for value in roi)
        x0, y0 = max(0, int(x * w)), max(0, int(y * h))
        x1, y1 = min(w, max(x0 + 2, int((x + rw) * w))), min(h, max(y0 + 2, int((y + rh) * h)))
        crop = frame[y0:y1, x0:x1]
        scale = min(1.0, self.width / max(1, crop.shape[1]))
        if scale < 1.0:
            crop = cv2.resize(crop, (max(16, int(crop.shape[1] * scale)), max(16, int(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        line = None
        if foul_line is not None and len(foul_line) == 2:
            points = []
            for px, py in foul_line:
                points.append(((float(px) * w - x0) * scale, (float(py) * h - y0) * scale))
            line = (points[0], points[1])
        sample = _Sample(int(timestamp_ns), crop.copy(), line)
        try:
            self._queue.put_nowait(sample)
        except Full:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Empty:
                pass
            try:
                self._queue.put_nowait(sample)
            except Full:
                pass

    @staticmethod
    def _metrics(previous: np.ndarray, current: np.ndarray,
                 line: tuple[tuple[float, float], tuple[float, float]] | None) -> tuple[float, float]:
        previous_gray = cv2.GaussianBlur(cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        current_gray = cv2.GaussianBlur(cv2.cvtColor(current, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        delta = cv2.absdiff(previous_gray, current_gray)
        threshold = max(14, int(np.percentile(delta, 88)))
        mask = (delta >= threshold).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        total = float(mask.size)
        motion = float(cv2.countNonZero(mask)) / max(1.0, total)
        proximity = 0.0 if line else 1.0
        if line:
            a = np.asarray(line[0], np.float32)
            b = np.asarray(line[1], np.float32)
            vector = b - a
            denominator = max(1e-6, float(np.linalg.norm(vector)))
            corridor = max(6.0, min(current.shape[:2]) * .12)
            for contour in contours:
                area = float(cv2.contourArea(contour))
                if not total * .002 <= area <= total * .30:
                    continue
                # The relevant evidence is the nearest moving edge, not the
                # centre of the athlete-shaped contour. A centroid can remain
                # far from the foul line while the shoe crosses it.
                points = contour.reshape(-1, 2).astype(np.float32)
                relative = points - a
                distances = np.abs(vector[0] * relative[:, 1] - vector[1] * relative[:, 0]) / denominator
                distance = float(np.min(distances))
                # If the foul line passes through the filled moving region, its
                # boundary points can still be several pixels away. Sample the
                # short line segment so an actual intersection scores as zero.
                for fraction in np.linspace(0.0, 1.0, 16):
                    line_point = a + vector * fraction
                    if cv2.pointPolygonTest(contour, (float(line_point[0]), float(line_point[1])), False) >= 0:
                        distance = 0.0
                        break
                proximity = max(proximity, math.exp(-distance / corridor))
        return motion, proximity

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self._queue.get(timeout=.1)
            except Empty:
                continue
            try:
                if not self._enabled:
                    continue
                if self._previous is None or self._previous.shape != sample.roi_bgr.shape:
                    self._previous = sample.roi_bgr
                    self.state = MonitorState.ARMING
                    continue
                motion, proximity = self._metrics(self._previous, sample.roi_bgr, sample.line)
                self.last_motion = motion
                self.last_proximity = proximity
                self._previous = sample.roi_bgr
                now = time.perf_counter()
                if now < self._cooldown_until:
                    self.state = MonitorState.COOLDOWN
                    continue
                active = motion >= .008 and proximity >= .24
                quiet = motion <= .010
                if self.state in {MonitorState.DISARMED, MonitorState.ARMING, MonitorState.COOLDOWN}:
                    self.state = MonitorState.ARMING
                    self._still_frames = self._still_frames + 1 if quiet else 0
                    if self._still_frames >= 4:
                        self.state = MonitorState.ARMED
                elif self.state is MonitorState.ARMED:
                    if active:
                        self.state = MonitorState.APPROACH
                        self._active_frames = 1
                        self._quiet_after_active = 0
                        self._peak = (motion * (.55 + .45 * proximity), sample.timestamp_ns)
                        self._first_active_timestamp_ns = sample.timestamp_ns
                elif self.state is MonitorState.APPROACH:
                    if active:
                        self._active_frames += 1
                        self._quiet_after_active = 0
                        score = motion * (.55 + .45 * proximity)
                        if score > self._peak[0]:
                            self._peak = (score, sample.timestamp_ns)
                    elif quiet:
                        self._quiet_after_active += 1
                    strong_single_sample = self._peak[0] >= .050
                    if (self._active_frames >= 2 or strong_single_sample) and (self._quiet_after_active >= 2 or self._active_frames >= 18):
                        confidence = max(.0, min(1.0, self._peak[0] / .055))
                        # The later motion peak is commonly the shoe leaving
                        # or a following shadow. Analyse the first near-line
                        # activity, while the shoe is still in the frame.
                        event_timestamp_ns = self._first_active_timestamp_ns or self._peak[1]
                        event = TakeoffEvent(event_timestamp_ns, confidence)
                        self._cooldown_until = now + self.cooldown_seconds
                        self.state = MonitorState.COOLDOWN
                        self._still_frames = self._active_frames = self._quiet_after_active = 0
                        self._peak = (0.0, 0)
                        self._first_active_timestamp_ns = 0
                        _LOGGER.info(
                            "automatic_takeoff_event timestamp_ns=%s confidence=%.3f motion=%.4f proximity=%.3f",
                            event.timestamp_ns, event.confidence, self.last_motion, self.last_proximity,
                        )
                        self.callback(event)
                    elif self._active_frames + self._quiet_after_active > 32:
                        self.state = MonitorState.ARMING
                        self._still_frames = self._active_frames = self._quiet_after_active = 0
                        self._first_active_timestamp_ns = 0
            except Exception:
                _LOGGER.exception("automatic take-off live gate failed")
                self.reset()
            finally:
                self._queue.task_done()


def analyse_attempt(packets: Sequence[FramePacket], target_timestamp_ns: int,
                    roi: tuple[float, float, float, float], calibration: ProjectionCalibration,
                    *, before_seconds: float = .65, after_seconds: float = .30,
                    target_width: int = 256,
                    foul_area: Sequence[Sequence[float]] = (),
                    candidate: TakeoffCandidate | None = None) -> AutomaticAdvisory:
    """Create a conservative temporal advisory from a bounded attempt window."""
    started = time.perf_counter()
    fallback_index = (
        min(range(len(packets)), key=lambda index: abs(packets[index].timestamp_ns - target_timestamp_ns))
        if packets else 0
    )
    candidate = candidate or detect_takeoff_candidate(
        packets, target_timestamp_ns, roi, before_seconds, after_seconds, target_width,
    )
    if candidate is None:
        return AutomaticAdvisory(AdvisoryStatus.REVIEW, 0.0, fallback_index, None, None,
                                 "No reliable take-off frame was found.", (time.perf_counter() - started) * 1000)
    selected = sorted(set((candidate.frame_index, *candidate.usable_frame_indices)))
    selected = sorted(selected, key=lambda index: (abs(index - candidate.frame_index), index))[:3]
    reference_indices = [max(0, min(len(packets) - 1, candidate.frame_index + offset)) for offset in (-8, -6, 6, 8)]
    analysis_width = max(480, min(720, int(target_width) * 3))

    def reduced(index: int) -> np.ndarray:
        frame = decode_packet(packets[index])
        scale = min(1.0, analysis_width / max(1, frame.shape[1]))
        if scale < 1.0:
            frame = cv2.resize(frame, (max(1, int(frame.shape[1] * scale)), max(1, int(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        return frame

    references = [reduced(index) for index in sorted(set(reference_indices)) if index not in selected]
    measurements: list[tuple[int, object, bool, float, float, float]] = []
    for index in selected:
        frame = reduced(index)
        estimate = estimate_foot_polygon(frame, references, roi, calibration.board_corners, calibration.foul_line, calibration)
        if estimate is None:
            continue
        measurement = measure_projected_foot(estimate.polygon_px, calibration, (frame.shape[1], frame.shape[0]), estimate.confidence)
        xs = [point[0] for point in estimate.polygon_px]
        ys = [point[1] for point in estimate.polygon_px]
        x, y, rw, rh = roi
        margin = max(3.0, min(frame.shape[:2]) * .004)
        clipped = min(xs) <= x * frame.shape[1] + margin or max(xs) >= (x + rw) * frame.shape[1] - margin or min(ys) <= y * frame.shape[0] + margin or max(ys) >= (y + rh) * frame.shape[0] - margin
        overlap_px, overlap_ratio = shoe_foul_area_overlap(
            estimate.polygon_px, foul_area, (frame.shape[1], frame.shape[0]),
        )
        measurements.append((index, measurement, clipped, overlap_px, overlap_ratio, estimate.confidence))
    elapsed = (time.perf_counter() - started) * 1000
    if not measurements:
        return AutomaticAdvisory(AdvisoryStatus.REVIEW, candidate.confidence, candidate.frame_index, None, None,
                                 "The shoe outline was not reliable enough.", elapsed)
    if len(foul_area) == 4:
        area_over = [
            row for row in measurements
            if row[3] >= 4.0 and row[4] >= .002
        ]
        if area_over:
            index, item, _clipped, _overlap_px, overlap_ratio, shoe_confidence = max(
                area_over, key=lambda row: (row[4], row[3]),
            )
            confidence = min(candidate.confidence, item.confidence, shoe_confidence)
            if confidence >= .70:
                return AutomaticAdvisory(
                    AdvisoryStatus.FOUL, confidence, index,
                    item.signed_clearance_cm, item.uncertainty_cm,
                    f"The detected shoe intersects the selected foul area ({overlap_ratio:.1%} of the shoe).",
                    elapsed, engine="foul-area-contact-v1",
                )
            return AutomaticAdvisory(
                AdvisoryStatus.REVIEW, confidence, index,
                item.signed_clearance_cm, item.uncertainty_cm,
                "Possible contact with the selected foul area was found, but shoe confidence is too low.",
                elapsed, engine="foul-area-contact-v1",
            )
    over = [] if len(foul_area) == 4 else [(index, item, clipped) for index, item, clipped, *_rest in measurements if item.signed_clearance_cm < -item.uncertainty_cm]
    clear = [(index, item, clipped) for index, item, clipped, *_rest in measurements if item.signed_clearance_cm > item.uncertainty_cm and not clipped]
    if len(over) >= 2:
        index, item, _clipped = min(over, key=lambda row: row[1].signed_clearance_cm)
        confidence = min(candidate.confidence, sum(row[1].confidence for row in over) / len(over))
        if confidence >= .72:
            return AutomaticAdvisory(AdvisoryStatus.FOUL, confidence, index, item.signed_clearance_cm,
                                     item.uncertainty_cm, "The sole edge crossed the calibrated foul plane in consecutive frames.", elapsed)
    if len(clear) >= 3 and len(clear) == len(measurements):
        index, item, _clipped = min(clear, key=lambda row: row[1].signed_clearance_cm)
        confidence = min(candidate.confidence, sum(row[1].confidence for row in clear) / len(clear))
        if confidence >= .82:
            return AutomaticAdvisory(AdvisoryStatus.VALID, confidence, index, item.signed_clearance_cm,
                                     item.uncertainty_cm, "The complete visible sole stayed behind the calibrated foul plane.", elapsed)
    nearest = min(measurements, key=lambda row: abs(row[1].signed_clearance_cm))
    return AutomaticAdvisory(AdvisoryStatus.REVIEW, min(candidate.confidence, nearest[1].confidence), nearest[0],
                             nearest[1].signed_clearance_cm, nearest[1].uncertainty_cm,
                             "The image, edge distance, or temporal agreement is not strong enough for automatic advice.", elapsed)
