from __future__ import annotations

from dataclasses import dataclass, replace
import ctypes
import logging
import math
import os
import time
from queue import Empty, Queue
from threading import Event, Lock, Thread
import tkinter as tk
from tkinter import ttk
from typing import Callable, Sequence

import cv2
import numpy as np
from PIL import Image, ImageTk

from .exporter import decode_packet
from .models import FramePacket
from .motion_segmentation import foreground_motion_mask
from .shoe_reconstruction import (
    ReconstructionCancelled,
    ReconstructionResult,
    ReconstructionTimedOut,
    checkerboard_asset_path,
    estimate_camera_profile,
    reconstruct_shoe_overhead,
)
from .theme import bind_resize_only, center_popup


STANDARD_BOARD_LENGTH_CM = 120.1
STANDARD_BOARD_WIDTH_CM = 34.0

_LOGGER = logging.getLogger("long_jump_replay.projection")
_UNDISTORT_CACHE_LOCK = Lock()
_UNDISTORT_MAP_CACHE: dict[tuple[object, ...], tuple[np.ndarray, np.ndarray]] = {}


@dataclass(frozen=True, slots=True)
class ProjectionCalibration:
    board_corners: tuple[tuple[float, float], ...]
    foul_line: tuple[tuple[float, float], ...]
    camera_signature: str = ""
    reference_width: int = 0
    reference_height: int = 0
    pad_length_cm: float = 0.0
    pad_width_cm: float = 0.0
    shoe_width_cm: float = 0.0
    legal_side_flipped: bool = False
    camera_profile: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ProjectionCandidate:
    frame_index: int
    timestamp_ns: int
    frame_bgr: np.ndarray
    score: float
    sharpness: float
    motion: float


@dataclass(frozen=True, slots=True)
class FootEstimate:
    polygon_px: tuple[tuple[float, float], ...]
    confidence: float
    search_roi_px: tuple[float, float, float, float] = ()
    candidate_polygons_px: tuple[tuple[tuple[float, float], ...], ...] = ()


@dataclass(frozen=True, slots=True)
class ProjectionAnalysisResult:
    calibration: ProjectionCalibration
    board_points_px: tuple[tuple[float, float], ...]
    foul_points_px: tuple[tuple[float, float], ...]
    shoe_points_px: tuple[tuple[float, float], ...]
    shoe_confidence: float
    diagnostics: tuple[str, ...] = ()
    shoe_search_roi_px: tuple[float, float, float, float] = ()
    shoe_candidate_points_px: tuple[tuple[tuple[float, float], ...], ...] = ()


def _client_animations_enabled() -> bool:
    """Respect Windows' client-area animation preference and test overrides."""
    override = os.environ.get("LONGJUMPREPLAY_REDUCED_MOTION", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return False
    if os.name != "nt":
        return True
    try:
        enabled = ctypes.c_int(1)
        # SPI_GETCLIENTAREAANIMATION
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return bool(enabled.value)
    except (AttributeError, OSError):
        pass
    return True


def _strong_ease_out(progress: float) -> float:
    """Evaluate cubic-bezier(0.23, 1, 0.32, 1) at a time fraction."""
    target = max(0.0, min(1.0, float(progress)))
    low, high = 0.0, 1.0
    parameter = target
    for _ in range(10):
        parameter = (low + high) * .5
        inverse = 1.0 - parameter
        x = 3.0 * inverse * inverse * parameter * .23 + 3.0 * inverse * parameter * parameter * .32 + parameter ** 3
        if x < target:
            low = parameter
        else:
            high = parameter
    inverse = 1.0 - parameter
    return 3.0 * inverse * inverse * parameter + 3.0 * inverse * parameter * parameter + parameter ** 3


@dataclass(frozen=True, slots=True)
class ProjectionMeasurement:
    polygon: tuple[tuple[float, float], ...]
    signed_clearance_cm: float
    uncertainty_cm: float
    status: str
    nearest_shoe_point: tuple[float, float]
    nearest_line_point: tuple[float, float]
    confidence: float

    @property
    def centre(self) -> tuple[float, float]:
        points = np.asarray(self.polygon, dtype=np.float32)
        centre = points.mean(axis=0)
        return float(centre[0]), float(centre[1])

    @property
    def distance_to_foul_line_cm(self) -> float:
        """Backward-compatible magnitude; judging uses signed_clearance_cm."""
        return abs(self.signed_clearance_cm)

    @property
    def crosses_foul_line(self) -> bool:
        return self.signed_clearance_cm < 0.0

    def display_text(self) -> str:
        if self.status == "touching":
            return f"0.0 cm touching ±{self.uncertainty_cm:.1f} cm"
        sign = "+" if self.signed_clearance_cm >= 0 else "−"
        label = "clear" if self.signed_clearance_cm >= 0 else "over"
        return f"{sign}{abs(self.signed_clearance_cm):.1f} cm {label} ±{self.uncertainty_cm:.1f} cm"


def measurement_display_text_ascii(measurement: ProjectionMeasurement) -> str:
    """ASCII-safe raster label; OpenCV Hershey fonts lack minus/plus-minus glyphs."""
    if measurement.status == "touching":
        return f"0.0 cm touching +/-{measurement.uncertainty_cm:.1f} cm"
    sign = "+" if measurement.signed_clearance_cm >= 0 else "-"
    label = "clear" if measurement.signed_clearance_cm >= 0 else "over"
    return f"{sign}{abs(measurement.signed_clearance_cm):.1f} cm {label} +/-{measurement.uncertainty_cm:.1f} cm"


def projection_verdict_text(status: str) -> str:
    """Return the evidence-view classification without implying a saved decision."""
    if status in {"review", "uncertain", "unknown"}:
        return "REVIEW ORIGINAL"
    if status == "over":
        return "FOUL"
    if status == "touching":
        return "ON THE LINE"
    return "VALID"


def projection_verdict_color(status: str) -> tuple[int, int, int]:
    """OpenCV BGR colour for the classification label."""
    if status in {"review", "uncertain", "unknown"}:
        return (190, 200, 215)
    if status == "over":
        return (90, 90, 255)
    if status == "touching":
        return (70, 205, 255)
    return (130, 220, 90)


def _validate_quad(points: Sequence[Sequence[float]]) -> np.ndarray:
    array = np.asarray(points, dtype=np.float32)
    if array.shape != (4, 2) or not np.isfinite(array).all():
        raise ValueError("Four finite board corner points are required")
    if abs(float(cv2.contourArea(array.reshape((-1, 1, 2))))) < 1e-4 or not cv2.isContourConvex(array.reshape((-1, 1, 2))):
        raise ValueError("Board corners must form a convex quadrilateral")
    return array


def order_board_corners(points: Sequence[Sequence[float]]) -> np.ndarray:
    """Return four clicked corners as top-left, top-right, bottom-right, bottom-left."""
    array = np.asarray(points, dtype=np.float32)
    if array.shape != (4, 2) or not np.isfinite(array).all():
        raise ValueError("Click all four board corners")
    hull = cv2.convexHull(array.reshape((-1, 1, 2))).reshape((-1, 2))
    if len(hull) != 4:
        raise ValueError("Board corners must surround the whole board")
    start = int(np.argmin(hull.sum(axis=1)))
    ordered = np.roll(hull, -start, axis=0)
    if ordered[1, 0] < ordered[-1, 0]:
        ordered = np.concatenate((ordered[:1], ordered[:0:-1]), axis=0)
    return _validate_quad(ordered)


def create_projection_calibration(
    board_points_px: Sequence[Sequence[float]],
    foul_points_px: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
    camera_signature: str,
    previous: ProjectionCalibration | None = None,
) -> ProjectionCalibration:
    """Create a complete calibration without asking the operator for dimensions."""
    width, height = int(frame_size[0]), int(frame_size[1])
    if width <= 1 or height <= 1:
        raise ValueError("A camera frame is required")
    board = order_board_corners(board_points_px)
    foul = np.asarray(foul_points_px, dtype=np.float32)
    if foul.shape != (2, 2) or not np.isfinite(foul).all():
        raise ValueError("Click both ends of the foul line")
    scale = np.asarray([width, height], dtype=np.float32)
    previous_is_old_default = bool(
        previous
        and abs(previous.pad_length_cm - 122.0) < 0.01
        and abs(previous.pad_width_cm - 20.0) < 0.01
    )
    length_cm = previous.pad_length_cm if previous and previous.pad_length_cm > 0 and not previous_is_old_default else STANDARD_BOARD_LENGTH_CM
    width_cm = previous.pad_width_cm if previous and previous.pad_width_cm > 0 and not previous_is_old_default else STANDARD_BOARD_WIDTH_CM
    shoe_width_cm = previous.shoe_width_cm if previous else 0.0
    return ProjectionCalibration(
        tuple((float(x), float(y)) for x, y in board / scale),
        tuple((float(x), float(y)) for x, y in foul / scale),
        camera_signature,
        width,
        height,
        length_cm,
        width_cm,
        shoe_width_cm,
        previous.legal_side_flipped if previous else False,
        previous.camera_profile if previous else None,
    )


def compute_pad_homography(
    board_corners: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
    output_size: tuple[int, int] = (900, 300),
) -> np.ndarray:
    """Map normalized source-image corners to a rectangular pad image."""
    width, height = int(frame_size[0]), int(frame_size[1])
    output_width, output_height = int(output_size[0]), int(output_size[1])
    if width <= 1 or height <= 1 or output_width <= 1 or output_height <= 1:
        raise ValueError("Frame and output dimensions must be positive")
    source = _validate_quad(board_corners).copy()
    source[:, 0] *= width
    source[:, 1] *= height
    destination = np.asarray(
        [[0, 0], [output_width - 1, 0], [output_width - 1, output_height - 1], [0, output_height - 1]],
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(source, destination)


def compute_physical_pad_homography(
    board_corners: Sequence[Sequence[float]],
    foul_line: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
    output_size: tuple[int, int] = (900, 300),
) -> np.ndarray:
    """Map the calibrated board into physical long-axis-horizontal coordinates."""
    width, height = int(frame_size[0]), int(frame_size[1])
    output_width, output_height = int(output_size[0]), int(output_size[1])
    source = _validate_quad(board_corners).copy()
    source[:, 0] *= width
    source[:, 1] *= height
    foul_source = np.asarray(foul_line, dtype=np.float32) * np.asarray([width, height], dtype=np.float32)
    normalized_foul = cv2.perspectiveTransform(
        foul_source.reshape((-1, 1, 2)), compute_pad_homography(board_corners, frame_size, (1001, 1001))
    ).reshape((-1, 2)) / 1000.0
    horizontal = abs(float(normalized_foul[1, 0] - normalized_foul[0, 0])) >= abs(float(normalized_foul[1, 1] - normalized_foul[0, 1]))
    if horizontal:
        destination = np.asarray([[0, 0], [output_width - 1, 0], [output_width - 1, output_height - 1], [0, output_height - 1]], dtype=np.float32)
    else:
        # Normalized x is the physical short axis and normalized y is the
        # physical long axis; transpose them without an additional mirror.
        destination = np.asarray([[0, 0], [0, output_height - 1], [output_width - 1, output_height - 1], [output_width - 1, 0]], dtype=np.float32)
    return cv2.getPerspectiveTransform(source, destination)


def undistort_frame_for_projection(frame: np.ndarray, calibration: ProjectionCalibration) -> np.ndarray:
    """Apply an optional calibrated radial profile before board rectification."""
    profile = calibration.camera_profile or {}
    if not profile or frame is None:
        return frame
    height, width = frame.shape[:2]
    try:
        matrix = np.asarray(profile.get("camera_matrix"), dtype=np.float32) if profile.get("camera_matrix") is not None else None
        distortion = np.asarray(profile.get("distortion"), dtype=np.float32).reshape(-1, 1) if profile.get("distortion") is not None else None
        if matrix is None or matrix.shape != (3, 3):
            focal = float(max(width, height))
            matrix = np.asarray([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]], dtype=np.float32)
        if distortion is None or distortion.size < 1:
            k1 = float(profile.get("radial_k1", 0.0) or 0.0)
            distortion = np.asarray([[k1], [0.0], [0.0], [0.0], [0.0]], dtype=np.float32)
        # Calibration remains stable for a camera session. Reuse OpenCV's
        # expensive per-pixel mapping and only remap each requested frame.
        key = (width, height, matrix.tobytes(), distortion.tobytes())
        with _UNDISTORT_CACHE_LOCK:
            maps = _UNDISTORT_MAP_CACHE.get(key)
        if maps is None:
            maps = cv2.initUndistortRectifyMap(matrix, distortion, None, matrix, (width, height), cv2.CV_16SC2)
            with _UNDISTORT_CACHE_LOCK:
                if len(_UNDISTORT_MAP_CACHE) >= 8:
                    _UNDISTORT_MAP_CACHE.pop(next(iter(_UNDISTORT_MAP_CACHE)))
                _UNDISTORT_MAP_CACHE[key] = maps
        return cv2.remap(frame, maps[0], maps[1], interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    except (TypeError, ValueError, cv2.error):
        return frame


def undistort_points_for_projection(
    points_px: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
    calibration: ProjectionCalibration,
) -> np.ndarray:
    """Apply the same optional lens profile to geometry as to image pixels."""
    points = np.asarray(points_px, dtype=np.float32).reshape((-1, 1, 2))
    profile = calibration.camera_profile or {}
    if not profile:
        return points.reshape((-1, 2))
    width, height = frame_size
    try:
        matrix = np.asarray(profile.get("camera_matrix"), dtype=np.float32) if profile.get("camera_matrix") is not None else None
        distortion = np.asarray(profile.get("distortion"), dtype=np.float32).reshape(-1, 1) if profile.get("distortion") is not None else None
        if matrix is None or matrix.shape != (3, 3):
            focal = float(max(width, height)); matrix = np.asarray([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]], np.float32)
        if distortion is None or distortion.size < 1:
            distortion = np.asarray([[float(profile.get("radial_k1", 0.0) or 0.0)], [0], [0], [0], [0]], np.float32)
        return cv2.undistortPoints(points, matrix, distortion, P=matrix).reshape((-1, 2))
    except (TypeError, ValueError, cv2.error):
        return points.reshape((-1, 2))


def corrected_projection_calibration(calibration: ProjectionCalibration, frame_size: tuple[int, int]) -> ProjectionCalibration:
    if not calibration.camera_profile:
        return calibration
    scale = np.asarray(frame_size, np.float32)
    board_px = np.asarray(calibration.board_corners, np.float32) * scale
    foul_px = np.asarray(calibration.foul_line, np.float32) * scale
    board = undistort_points_for_projection(board_px, frame_size, calibration) / scale
    foul = undistort_points_for_projection(foul_px, frame_size, calibration) / scale
    return replace(calibration, board_corners=tuple(map(tuple, board.tolist())), foul_line=tuple(map(tuple, foul.tolist())), camera_profile=None)


def detect_board_corners(frame: np.ndarray, roi: Sequence[float] | None = None) -> tuple[tuple[float, float], ...] | None:
    """Find a light board using colour context, geometry and its dark strip."""
    started = time.perf_counter()
    if frame is None or frame.size == 0:
        return None
    height, width = frame.shape[:2]
    crop = frame
    ox = oy = 0
    if roi is not None and len(roi) == 4:
        x, y, rw, rh = [float(value) for value in roi]
        ox, oy = max(0, int(x * width)), max(0, int(y * height))
        x1, y1 = min(width, int((x + rw) * width)), min(height, int((y + rh) * height))
        if x1 > ox + 20 and y1 > oy + 20:
            crop = frame[oy:y1, ox:x1]
    # Detection is bounded because startup calibration can receive a 4K frame.
    analysis_scale = min(1.0, 1100.0 / max(crop.shape[:2]))
    analysed = crop if analysis_scale >= 1.0 else cv2.resize(crop, None, fx=analysis_scale, fy=analysis_scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(analysed, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(analysed, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(analysed, cv2.COLOR_BGR2LAB)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    otsu_value, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    light_floor = max(118.0, min(225.0, float(np.percentile(lab[:, :, 0], 68))))
    neutral_light = ((lab[:, :, 0] >= light_floor) & ((hsv[:, :, 1] <= 105) | (gray >= max(175.0, otsu_value)))).astype(np.uint8) * 255
    bright = cv2.bitwise_or(otsu, neutral_light)
    short_side = min(analysed.shape[:2])
    close_radius = max(2, min(8, int(round(short_side * .012))))
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_radius * 2 + 1, close_radius * 2 + 1))
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    edges = cv2.Canny(blurred, 38, 125)
    bright_contours, _ = cv2.findContours(bright, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    red_track = ((((hue <= 14) | (hue >= 165)) & (saturation >= 55) & (hsv[:, :, 2] >= 35)) | ((lab[:, :, 1] >= 143) & (lab[:, :, 1] > lab[:, :, 2] + 4))).astype(np.uint8)
    best: np.ndarray | None = None
    best_score = 0.0
    analysed_area = float(analysed.shape[0] * analysed.shape[1])
    for contour in bright_contours:
        area = abs(float(cv2.contourArea(contour)))
        if area < analysed_area * .004 or area > analysed_area * .78:
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        hull = cv2.convexHull(contour)
        approx = cv2.approxPolyDP(hull, .025 * cv2.arcLength(hull, True), True)
        rect = cv2.minAreaRect(contour)
        rect_width, rect_height = rect[1]
        long_side = max(rect_width, rect_height)
        narrow_side = max(1.0, min(rect_width, rect_height))
        elongation = long_side / narrow_side
        if long_side < short_side * .16 or narrow_side < 4 or elongation < 1.35 or elongation > 28.0:
            continue
        candidate = approx.reshape((-1, 2)).astype(np.float32) if len(approx) == 4 and cv2.isContourConvex(approx) else cv2.boxPoints(rect).astype(np.float32)
        try:
            ordered = order_board_corners(candidate)
        except ValueError:
            continue
        candidate_mask = np.zeros(gray.shape, np.uint8)
        cv2.fillConvexPoly(candidate_mask, np.rint(ordered).astype(np.int32), 255)
        candidate_pixels = candidate_mask > 0
        pixel_count = int(np.count_nonzero(candidate_pixels))
        if pixel_count < 20:
            continue
        box_area = max(1.0, float(rect_width * rect_height))
        rectangularity = min(1.0, area / box_area)
        light_fraction = float(np.count_nonzero((bright > 0) & candidate_pixels)) / pixel_count
        # A real embedded board is normally surrounded by tartan. The score is
        # useful when available but deliberately optional for indoor fixtures.
        ring_radius = max(4, int(round(narrow_side * .55)))
        ring_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ring_radius * 2 + 1, ring_radius * 2 + 1))
        ring = (cv2.dilate(candidate_mask, ring_kernel) > 0) & ~candidate_pixels
        red_context = float(np.count_nonzero((red_track > 0) & ring)) / max(1, int(np.count_nonzero(ring)))
        inside_mean = float(np.mean(gray[candidate_pixels]))
        ring_mean = float(np.mean(gray[ring])) if np.any(ring) else inside_mean
        contrast = max(0.0, min(1.0, (inside_mean - ring_mean) / 85.0))

        canonical = np.asarray([[0, 0], [479, 0], [479, 139], [0, 139]], np.float32)
        rectified = cv2.warpPerspective(gray, cv2.getPerspectiveTransform(ordered.astype(np.float32), canonical), (480, 140))
        interior = rectified[:, 28:-28].astype(np.float32)
        row_darkness = np.median(interior) - np.mean(interior, axis=1)
        row_gradient = np.mean(np.abs(cv2.Sobel(interior, cv2.CV_32F, 0, 1, ksize=3)), axis=1)
        margin = 12
        line_strength = 0.0
        if len(row_darkness) > margin * 2:
            line_strength = min(1.0, max(0.0, (float(np.max(row_darkness[margin:-margin])) - 7.0) / 38.0))
            line_strength = max(line_strength, min(1.0, max(0.0, (float(np.max(row_gradient[margin:-margin])) - 5.0) / 35.0)))

        area_score = min(1.0, area / (analysed_area * .055))
        elongation_score = min(1.0, max(0.0, (elongation - 1.25) / 2.3))
        score = (
            .22 * rectangularity
            + .19 * light_fraction
            + .15 * contrast
            + .13 * area_score
            + .12 * elongation_score
            + .11 * red_context
            + .08 * line_strength
        )
        if score > best_score:
            best_score = score
            best = ordered / analysis_scale
    if best is None:
        # Partial visibility remains an editable fallback. It uses line support
        # only after colour/geometry candidates have failed.
        light_support = cv2.dilate(bright, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        points = cv2.findNonZero(cv2.bitwise_and(edges, light_support))
        if points is None or len(points) < 20:
            return None
        fallback_rect = cv2.minAreaRect(points)
        fallback_long = max(fallback_rect[1])
        fallback_short = max(1.0, min(fallback_rect[1]))
        if fallback_long / fallback_short < 1.3 or fallback_short < 4.0:
            return None
        best = cv2.boxPoints(fallback_rect).astype(np.float32) / analysis_scale
    best[:, 0] += ox
    best[:, 1] += oy
    try:
        ordered = order_board_corners(best)
    except ValueError:
        return None
    result = tuple((float(x), float(y)) for x, y in ordered)
    _LOGGER.info("board_detection duration_ms=%.2f score=%.3f red_context_used=%s", (time.perf_counter() - started) * 1000.0, best_score, bool(np.any(red_track)))
    return result


def detect_foul_line(
    frame: np.ndarray,
    board_points_px: Sequence[Sequence[float]],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Locate a dark, well-supported internal strip parallel to the long edges."""
    started = time.perf_counter()
    board = order_board_corners(board_points_px)
    horizontal_length = (np.linalg.norm(board[1] - board[0]) + np.linalg.norm(board[2] - board[3])) / 2.0
    vertical_length = (np.linalg.norm(board[2] - board[1]) + np.linalg.norm(board[3] - board[0])) / 2.0
    output_width, output_height = 720, 204
    if horizontal_length >= vertical_length:
        destination = np.asarray([[0, 0], [output_width - 1, 0], [output_width - 1, output_height - 1], [0, output_height - 1]], np.float32)
    else:
        destination = np.asarray([[0, 0], [0, output_height - 1], [output_width - 1, output_height - 1], [output_width - 1, 0]], np.float32)
    transform = cv2.getPerspectiveTransform(board.astype(np.float32), destination)
    rectified = cv2.warpPerspective(frame, transform, (output_width, output_height))
    gray = cv2.GaussianBlur(cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    interior = gray[:, int(output_width * .06):int(output_width * .94)]
    gradient = np.abs(cv2.Sobel(interior, cv2.CV_32F, 0, 1, ksize=3))
    gradient_profile = np.mean(gradient, axis=1)
    baseline = float(np.median(interior))
    darkness_profile = np.maximum(0.0, baseline - np.mean(interior.astype(np.float32), axis=1))
    dark_threshold = max(18.0, baseline * .22)
    dark_coverage = np.mean(interior < baseline - dark_threshold, axis=1)
    profile = gradient_profile / max(1.0, float(np.percentile(gradient_profile, 90)))
    profile += darkness_profile / max(1.0, float(np.percentile(darkness_profile, 90)))
    profile += np.clip(dark_coverage / .42, 0.0, 1.0)
    margin = max(8, int(output_height * .10))
    if profile.size <= margin * 2:
        return None
    row = margin + int(np.argmax(profile[margin:-margin]))
    support = float(dark_coverage[row])
    gradient_support = float(gradient_profile[row])
    if float(profile[row]) < max(1.15, float(np.median(profile)) * 1.35) or (support < .16 and gradient_support < 8.0):
        return None
    inverse = np.linalg.inv(transform)
    line = np.asarray([[[0.0, float(row)]], [[float(output_width - 1), float(row)]]], np.float32)
    source = cv2.perspectiveTransform(line, inverse).reshape((-1, 2))
    result = (float(source[0, 0]), float(source[0, 1])), (float(source[1, 0]), float(source[1, 1]))
    _LOGGER.info("foul_line_detection duration_ms=%.2f support=%.3f", (time.perf_counter() - started) * 1000.0, max(support, min(1.0, gradient_support / 30.0)))
    return result


def smooth_closed_outline(points: Sequence[Sequence[float]], samples: int = 20) -> tuple[tuple[float, float], ...]:
    """Resample a closed contour into stable editable points for smooth display."""
    source = np.asarray(points, dtype=np.float32)
    if len(source) < 3:
        return tuple((float(x), float(y)) for x, y in source)
    closed = np.vstack((source, source[0]))
    lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    if cumulative[-1] <= 1e-6:
        return tuple((float(x), float(y)) for x, y in source)
    targets = np.linspace(0.0, cumulative[-1], max(8, int(samples)), endpoint=False)
    result = []
    for target in targets:
        index = min(len(lengths) - 1, int(np.searchsorted(cumulative, target, side="right") - 1))
        ratio = (target - cumulative[index]) / max(1e-6, lengths[index])
        point = closed[index] + (closed[index + 1] - closed[index]) * ratio
        result.append((float(point[0]), float(point[1])))
    return tuple(result)


def snap_brush_trace_to_edges(
    frame: np.ndarray,
    trace_points: Sequence[Sequence[float]],
    radius_px: int = 22,
    samples: int = 28,
) -> tuple[tuple[float, float], ...]:
    """Snap a roughly painted shoe boundary to nearby image edges.

    This is intentionally a fast editor aid: it uses only the already loaded
    frame and never starts segmentation or reconstruction from mouse events.
    """
    trace = np.asarray(trace_points, dtype=np.float32).reshape((-1, 2))
    if len(trace) < 3 or frame is None or frame.size == 0:
        return tuple((float(x), float(y)) for x, y in trace)
    trace = np.asarray(smooth_closed_outline(trace, samples=max(48, int(samples)*2)), np.float32)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 35, 35)
    edges = cv2.Canny(gray, 35, 110)
    gradient_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gradient_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(gradient_x, gradient_y)
    height, width = gray.shape
    radius = max(5, min(50, int(radius_px)))
    snapped: list[tuple[float, float]] = []
    for x, y in trace:
        cx, cy = int(round(x)), int(round(y))
        x0, x1 = max(0, cx - radius), min(width, cx + radius + 1)
        y0, y1 = max(0, cy - radius), min(height, cy + radius + 1)
        ys, xs = np.nonzero(edges[y0:y1, x0:x1])
        if len(xs):
            absolute_x, absolute_y = xs + x0, ys + y0
            distance = np.hypot(absolute_x - x, absolute_y - y)
            strength = gradient[absolute_y, absolute_x]
            score = distance - np.minimum(8.0, strength / 32.0)
            best = int(np.argmin(score))
            snapped.append((float(absolute_x[best]), float(absolute_y[best])))
        else:
            snapped.append((float(x), float(y)))
    # Remove nearly repeated mouse samples before stable closed resampling.
    filtered = [snapped[0]]
    for point in snapped[1:]:
        if math.hypot(point[0] - filtered[-1][0], point[1] - filtered[-1][1]) >= 2.0:
            filtered.append(point)
    return smooth_closed_outline(filtered, samples=max(12, min(48, int(samples))))


def foul_area_from_line_px(
    line: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
    thickness_px: float = 8.0,
) -> tuple[tuple[float, float], ...]:
    points = np.asarray(line, dtype=np.float32).reshape(2, 2)
    vector = points[1] - points[0]
    length = max(1e-6, float(np.linalg.norm(vector)))
    normal = np.asarray((-vector[1], vector[0]), np.float32) / length * max(2.0, thickness_px) * .5
    return tuple((float(x), float(y)) for x, y in (points[0] + normal, points[1] + normal, points[1] - normal, points[0] - normal))


def foul_line_from_area_px(
    area: Sequence[Sequence[float]],
    board_points_px: Sequence[Sequence[float]] = (),
) -> tuple[tuple[float, float], ...]:
    """Resolve the judging boundary from four foul-strip points in any order.

    The marked strip has two long edges.  When the board is available, the
    edge nearest its centre is the physical take-off line.  Without board
    geometry, return the centreline for backward-compatible callers.
    """
    points = np.asarray(area, dtype=np.float32).reshape(4, 2)
    if not np.isfinite(points).all():
        raise ValueError("Foul-area points must be finite")
    centre = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - centre[1], points[:, 0] - centre[0])
    ordered = points[np.argsort(angles)]
    edge_pairs = (
        ((ordered[0], ordered[1]), (ordered[2], ordered[3])),
        ((ordered[1], ordered[2]), (ordered[3], ordered[0])),
    )
    first_edge, second_edge = max(
        edge_pairs,
        key=lambda pair: sum(float(np.linalg.norm(edge[1] - edge[0])) for edge in pair),
    )
    if len(board_points_px) == 4:
        board_centre = np.asarray(board_points_px, dtype=np.float32).reshape(4, 2).mean(axis=0)
        selected = min(
            (first_edge, second_edge),
            key=lambda edge: float(np.linalg.norm((edge[0] + edge[1]) * .5 - board_centre)),
        )
        return tuple((float(point[0]), float(point[1])) for point in selected)
    direct = float(np.linalg.norm(first_edge[0] - second_edge[0]) + np.linalg.norm(first_edge[1] - second_edge[1]))
    crossed = float(np.linalg.norm(first_edge[0] - second_edge[1]) + np.linalg.norm(first_edge[1] - second_edge[0]))
    matched_second = second_edge if direct <= crossed else (second_edge[1], second_edge[0])
    centreline = (
        (first_edge[0] + matched_second[0]) * .5,
        (first_edge[1] + matched_second[1]) * .5,
    )
    return tuple((float(point[0]), float(point[1])) for point in centreline)


def estimate_radial_profile_from_board_edges(
    frame: np.ndarray,
    board_points_px: Sequence[Sequence[float]],
) -> dict[str, object] | None:
    """Fit a bounded one-coefficient lens model from curved board-edge samples."""
    height, width = frame.shape[:2]
    board = order_board_corners(board_points_px)
    edges = cv2.Canny(cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (5, 5), 0), 35, 120)
    ys, xs = np.nonzero(edges)
    all_points = np.column_stack((xs, ys)).astype(np.float32)
    if len(all_points) < 40:
        return None
    groups: list[np.ndarray] = []
    band = max(3.0, min(width, height) * .018)
    for index, start in enumerate(board):
        end = board[(index + 1) % 4]
        vector = end - start; denominator = max(1e-6, float(np.dot(vector, vector)))
        relative = all_points - start
        t = (relative @ vector) / denominator
        projected = start + t[:, None] * vector
        distance = np.linalg.norm(all_points - projected, axis=1)
        selected = all_points[(t >= -.03) & (t <= 1.03) & (distance <= band)]
        if len(selected) >= 18:
            groups.append(selected)
    if len(groups) < 2:
        return None
    focal = float(max(width, height))
    matrix = np.asarray([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]], np.float32)
    def residual(k1: float) -> float:
        distortion = np.asarray([k1, 0, 0, 0, 0], np.float32)
        total = 0.0; count = 0
        for group in groups:
            corrected = cv2.undistortPoints(group.reshape((-1, 1, 2)), matrix, distortion, P=matrix).reshape((-1, 2))
            centred = corrected - corrected.mean(axis=0)
            _u, _s, vh = np.linalg.svd(centred, full_matrices=False)
            normal = vh[-1]
            distances = centred @ normal
            total += float(np.sum(distances * distances)); count += len(distances)
        return math.sqrt(total / max(1, count))
    candidates = np.linspace(-.32, .24, 29)
    errors = [(residual(float(k1)), float(k1)) for k1 in candidates]
    base_error = residual(0.0)
    best_error, best_k1 = min(errors)
    if base_error < .35 or best_error >= base_error * .94 or abs(best_k1) < .015:
        return None
    return {
        "camera_matrix": matrix.tolist(),
        "distortion": [best_k1, 0.0, 0.0, 0.0, 0.0],
        "radial_k1": best_k1,
        "rms": best_error,
        "source": "board_edges",
    }


def filter_projection_candidates(
    candidates: Sequence[ProjectionCandidate],
    reference_frames: Sequence[np.ndarray],
    roi: Sequence[float],
    calibration: ProjectionCalibration | None,
) -> tuple[list[ProjectionCandidate], dict[int, FootEstimate]]:
    """Keep only frames with a plausible non-shadow shoe observation."""
    kept: list[ProjectionCandidate] = []
    estimates: dict[int, FootEstimate] = {}
    fallback_refs = [candidate.frame_bgr for candidate in candidates]
    for candidate in candidates[:7]:
        references = [frame for frame in reference_frames if frame is not None and frame.shape == candidate.frame_bgr.shape]
        if not references:
            references = [frame for frame in fallback_refs if frame is not candidate.frame_bgr and frame.shape == candidate.frame_bgr.shape]
        estimate = estimate_foot_polygon(
            candidate.frame_bgr,
            references[:6],
            roi,
            calibration.board_corners if calibration else None,
            calibration.foul_line if calibration else None,
            calibration,
        )
        if estimate is not None and estimate.confidence >= .28:
            kept.append(candidate)
            estimates[candidate.frame_index] = estimate
    return kept, estimates


def project_points_to_pad(
    points_px: Sequence[Sequence[float]],
    board_corners: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
) -> np.ndarray:
    """Return points in normalized pad coordinates, where (0, 0) is top-left."""
    homography = compute_pad_homography(board_corners, frame_size, (1001, 1001))
    points = np.asarray(points_px, dtype=np.float32).reshape((-1, 1, 2))
    projected = cv2.perspectiveTransform(points, homography).reshape((-1, 2))
    projected[:, 0] /= 1000.0
    projected[:, 1] /= 1000.0
    return projected


def unproject_points_from_pad(
    points: Sequence[Sequence[float]],
    board_corners: Sequence[Sequence[float]],
    frame_size: tuple[int, int],
) -> np.ndarray:
    """Map normalized board coordinates back to source-image pixels."""
    homography = compute_pad_homography(board_corners, frame_size, (1001, 1001))
    inverse = np.linalg.inv(homography)
    normalized = np.asarray(points, dtype=np.float32).reshape((-1, 1, 2)) * 1000.0
    return cv2.perspectiveTransform(normalized, inverse).reshape((-1, 2))


def _roi_bounds(frame: np.ndarray, roi: Sequence[float]) -> tuple[int, int, int, int]:
    height, width = frame.shape[:2]
    x, y, roi_width, roi_height = (float(value) for value in roi)
    x0 = max(0, min(width - 1, int(round(x * width))))
    y0 = max(0, min(height - 1, int(round(y * height))))
    x1 = max(x0 + 1, min(width, int(round((x + roi_width) * width))))
    y1 = max(y0 + 1, min(height, int(round((y + roi_height) * height))))
    return x0, y0, x1, y1


def board_search_roi(
    board_corners: Sequence[Sequence[float]],
    margin_ratio: float = .08,
) -> tuple[float, float, float, float]:
    """Return an expanded normalized ROI surrounding a calibrated board."""
    points = _validate_quad(board_corners)
    minimum = points.min(axis=0)
    maximum = points.max(axis=0)
    span = maximum - minimum
    margin = np.maximum(.04, span * max(0.0, float(margin_ratio)))
    start = np.maximum(0.0, minimum - margin)
    end = np.minimum(1.0, maximum + margin)
    return float(start[0]), float(start[1]), float(end[0] - start[0]), float(end[1] - start[1])


def _board_search_mask(
    crop_shape: tuple[int, int],
    frame_shape: tuple[int, int],
    crop_origin: tuple[int, int],
    board_corners: Sequence[Sequence[float]] | None,
) -> np.ndarray:
    mask = np.full(crop_shape, 255, dtype=np.uint8)
    if board_corners is None or len(board_corners) != 4:
        return mask
    frame_height, frame_width = frame_shape
    x0, y0 = crop_origin
    points = np.asarray(board_corners, dtype=np.float32) * np.asarray([frame_width, frame_height], dtype=np.float32)
    points -= np.asarray([x0, y0], dtype=np.float32)
    mask.fill(0)
    cv2.fillConvexPoly(mask, np.rint(points).astype(np.int32), 255)
    radius = max(8, int(round(min(crop_shape) * .28)))
    kernel_size = radius * 2 + 1
    return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)))


def _decode_safely(packet: FramePacket) -> np.ndarray | None:
    try:
        return decode_packet(packet)
    except (ValueError, cv2.error):
        return None


def _nearest_index(packets: Sequence[FramePacket], timestamp_ns: int) -> int:
    return min(range(len(packets)), key=lambda index: abs(packets[index].timestamp_ns - timestamp_ns))


def consecutive_candidate_indices(centre_index: int, frame_count: int, radius: int = 3) -> tuple[int, ...]:
    """Return up to seven unique consecutive frames, balanced at clip edges."""
    count = max(0, int(frame_count))
    if count == 0:
        return ()
    wanted = min(count, max(1, int(radius) * 2 + 1))
    centre = max(0, min(count - 1, int(centre_index)))
    start = max(0, min(centre - radius, count - wanted))
    return tuple(range(start, start + wanted))


def rank_projection_candidates(
    packets: Sequence[FramePacket],
    target_timestamp_ns: int,
    roi: Sequence[float],
    offsets_ms: Sequence[int] = (-60, -40, -20, 0, 20, 40, 60),
) -> list[ProjectionCandidate]:
    """Decode and rank a bounded frame shortlist around the take-off moment."""
    if not packets:
        return []
    selected_indices: list[int] = []
    for offset_ms in offsets_ms:
        index = _nearest_index(packets, int(target_timestamp_ns + offset_ms * 1_000_000))
        if index not in selected_indices:
            selected_indices.append(index)
    decoded: dict[int, np.ndarray] = {}
    for index in set(selected_indices):
        frame = _decode_safely(packets[index])
        if frame is not None:
            decoded[index] = frame
    decoded_frames = [(index, packets[index].timestamp_ns, frame) for index, frame in decoded.items()]
    return rank_decoded_projection_frames(decoded_frames, target_timestamp_ns, roi)


def rank_decoded_projection_frames(
    frames: Sequence[tuple[int, int, np.ndarray]],
    target_timestamp_ns: int,
    roi: Sequence[float],
) -> list[ProjectionCandidate]:
    """Rank already-decoded frames, including frames read from an attempt MP4."""
    if not frames:
        return []
    ordered_frames = sorted(
        ((int(index), int(timestamp_ns), frame) for index, timestamp_ns, frame in frames if frame is not None),
        key=lambda item: item[1],
    )
    if not ordered_frames:
        return []
    candidates: list[ProjectionCandidate] = []
    for position, (index, timestamp_ns, frame) in enumerate(ordered_frames):
        x0, y0, x1, y1 = _roi_bounds(frame, roi)
        crop = frame[y0:y1, x0:x1]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        sharpness = min(1.0, max(0.0, float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 800.0))
        references = [
            other_frame[y0:y1, x0:x1]
            for other_position, (_other_index, _other_timestamp, other_frame) in enumerate(ordered_frames)
            if other_position != position and other_frame.shape == frame.shape
        ]
        foreground, _shadow = foreground_motion_mask(crop, references)
        foreground_ratio = float(np.count_nonzero(foreground)) / max(1.0, float(foreground.size))
        motion = min(1.0, foreground_ratio / .10)
        distance_ms = abs(timestamp_ns - target_timestamp_ns) / 1_000_000.0
        proximity = math.exp(-distance_ms / 45.0)
        score = 0.58 * proximity + 0.24 * sharpness + 0.18 * motion
        candidates.append(ProjectionCandidate(index, timestamp_ns, frame, score, sharpness, motion))
    candidates.sort(key=lambda candidate: (-candidate.score, abs(candidate.timestamp_ns - target_timestamp_ns), candidate.frame_index))
    return candidates


def estimate_foot_polygon(
    frame: np.ndarray,
    reference_frames: Sequence[np.ndarray],
    roi: Sequence[float],
    board_corners: Sequence[Sequence[float]] | None = None,
    foul_line: Sequence[Sequence[float]] | None = None,
    physical_calibration: ProjectionCalibration | None = None,
) -> FootEstimate | None:
    """Estimate the complete visible shoe, not just the moving toe fragment.

    The old implementation selected one foreground component and convex-hulled
    it.  That loses the heel whenever the reference frames contain most of the
    shoe.  This version combines the strongest change against every reference,
    appearance change, and a bounded GrabCut refinement.  The returned contour
    intentionally keeps concavities; the contact/footprint fit may simplify it
    later, but the source overlay remains an image-supported boundary.
    """
    started = time.perf_counter()
    if frame is None or frame.ndim != 3 or not reference_frames:
        return None
    # Keep GrabCut bounded on 1080p/4K captures.  Contours are mapped back to
    # source pixels before returning, so this is a performance optimization,
    # not a loss of evidence resolution in the original frame.
    analysis_scale = min(1.0, 960.0 / max(frame.shape[1], frame.shape[0]))
    if analysis_scale < 1.0:
        small_frame = cv2.resize(frame, None, fx=analysis_scale, fy=analysis_scale, interpolation=cv2.INTER_AREA)
        small_refs = [cv2.resize(reference, (small_frame.shape[1], small_frame.shape[0]), interpolation=cv2.INTER_AREA) for reference in reference_frames if reference is not None and reference.shape == frame.shape]
        estimate = estimate_foot_polygon(small_frame, small_refs, roi, board_corners, foul_line, physical_calibration)
        if estimate is None:
            return None
        inverse = 1.0 / analysis_scale
        polygon = tuple((float(x * inverse), float(y * inverse)) for x, y in estimate.polygon_px)
        debug_roi = tuple(float(value * inverse) for value in estimate.search_roi_px)
        debug_candidates = tuple(
            tuple((float(x * inverse), float(y * inverse)) for x, y in candidate)
            for candidate in estimate.candidate_polygons_px
        )
        return FootEstimate(polygon, estimate.confidence, debug_roi, debug_candidates)
    # The visible heel and upper can extend well beyond the board in a side
    # view. The old narrow crop physically discarded them and returned only
    # the toe, so retain a generous but still board-anchored search region.
    effective_roi = board_search_roi(board_corners, margin_ratio=.72) if board_corners is not None and len(board_corners) == 4 else roi
    x0, y0, x1, y1 = _roi_bounds(frame, effective_roi)
    crop = frame[y0:y1, x0:x1]
    references = [reference[y0:y1, x0:x1] for reference in reference_frames if reference is not None and reference.shape == frame.shape]
    search_mask = _board_search_mask(crop.shape[:2], frame.shape[:2], (x0, y0), board_corners)
    motion_masks: list[np.ndarray] = []
    shadows: list[np.ndarray] = []
    for reference in references:
        local_mask, local_shadow = foreground_motion_mask(crop, [reference], search_mask)
        motion_masks.append(local_mask)
        shadows.append(local_shadow)
    mask = np.maximum.reduce(motion_masks) if motion_masks else np.zeros(crop.shape[:2], np.uint8)
    shadow = np.minimum.reduce(shadows) if shadows else np.zeros(crop.shape[:2], np.uint8)
    # Motion thresholding alone often leaves only a toe when the reference
    # frames still contain the heel. Compare against the least-similar clean
    # reference per pixel, then recover colour/texture changes outside shadows.
    current_lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.int16)
    deltas = []
    for reference in references:
        reference_lab = cv2.cvtColor(reference, cv2.COLOR_BGR2LAB).astype(np.int16)
        lightness_delta = np.abs(current_lab[:, :, 0] - reference_lab[:, :, 0])
        chroma_delta = np.linalg.norm(current_lab[:, :, 1:3] - reference_lab[:, :, 1:3], axis=2)
        deltas.append((lightness_delta, chroma_delta))
    max_lightness = np.maximum.reduce([item[0] for item in deltas])
    max_chroma = np.maximum.reduce([item[1] for item in deltas])
    appearance = (((max_chroma >= 10.0) & (max_lightness >= 4.0)) | (max_lightness >= 18.0)) & (shadow == 0)
    appearance &= search_mask > 0
    appearance_mask = appearance.astype(np.uint8) * 255
    join_radius = max(2, min(11, int(round(min(crop.shape[:2]) * .022))))
    join_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (join_radius * 2 + 1, join_radius * 2 + 1))
    appearance_mask = cv2.morphologyEx(appearance_mask, cv2.MORPH_CLOSE, join_kernel, iterations=2)
    mask = cv2.bitwise_or(mask, appearance_mask)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, join_kernel, iterations=2)
    mask[search_mask == 0] = 0
    # Remove the athlete's exposed leg before components are joined. Requiring
    # both skin-like chroma and saturation avoids classifying neutral floors,
    # white shoes or the board as skin on synthetic/indoor footage.
    ycrcb = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    skin = (
        (ycrcb[:, :, 1] >= 132)
        & (ycrcb[:, :, 1] <= 183)
        & (ycrcb[:, :, 2] >= 72)
        & (ycrcb[:, :, 2] <= 138)
        & (hsv[:, :, 1] >= 24)
        & (hsv[:, :, 2] >= 55)
        & ((hsv[:, :, 0] <= 28) | (hsv[:, :, 0] >= 172))
    ).astype(np.uint8) * 255
    skin = cv2.morphologyEx(skin, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    skin_reject = skin.copy()
    if board_corners is not None and len(board_corners) == 4:
        board_local = np.asarray(board_corners, np.float32) * np.asarray([frame.shape[1], frame.shape[0]], np.float32)
        board_local -= np.asarray([x0, y0], np.float32)
        board_mask = np.zeros(mask.shape, np.uint8)
        cv2.fillConvexPoly(board_mask, np.rint(board_local).astype(np.int32), 255)
        board_lengths = [float(np.linalg.norm(board_local[(index + 1) % 4] - board_local[index])) for index in range(4)]
        keep_radius = max(7, int(round(min(board_lengths) * .34)))
        near_board = cv2.dilate(board_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (keep_radius * 2 + 1, keep_radius * 2 + 1)))
        skin_reject[near_board > 0] = 0
    mask[skin_reject > 0] = 0
    if not np.any(mask):
        return None

    # Keep nearby fragments together, but only in the board search region. A
    # modest dilation reconnects sole/upper pieces without turning the board
    # into one giant foreground component.
    bridge_radius = max(4, min(28, int(round(min(crop.shape[:2]) * .060))))
    bridge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (bridge_radius * 2 + 1, bridge_radius * 2 + 1))
    seed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, bridge, iterations=1)
    # GrabCut is deliberately bounded to the expanded board ROI.  It snaps the
    # joined seed to real colour edges and removes the broad floor/background.
    try:
        gc_mask = np.full(seed.shape, cv2.GC_BGD, dtype=np.uint8)
        gc_mask[search_mask > 0] = cv2.GC_PR_BGD
        gc_mask[seed > 0] = cv2.GC_PR_FGD
        sure = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
        gc_mask[sure > 0] = cv2.GC_FGD
        # Shadows and exposed skin are never allowed to become certain shoe
        # pixels; GrabCut may retain only boundary pixels when evidence agrees.
        gc_mask[shadow > 0] = cv2.GC_PR_BGD
        gc_mask[skin_reject > 0] = cv2.GC_BGD
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        cv2.grabCut(crop, gc_mask, None, bgd_model, fgd_model, 2, cv2.GC_INIT_WITH_MASK)
        refined = np.where((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        refined[search_mask == 0] = 0
        if cv2.countNonZero(refined) >= max(30, int(cv2.countNonZero(mask) * .22)):
            mask = refined
    except (cv2.error, ValueError):
        # GrabCut is an enhancement, not a reason to lose a usable classical
        # mask on older OpenCV builds or very small synthetic fixtures.
        pass

    # Remove isolated specks while retaining concave shoe boundaries.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    crop_area = float(mask.shape[0] * mask.shape[1])
    edges = cv2.Canny(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 40, 125) > 0
    board_source = None
    board_long = float(max(crop.shape[:2]))
    board_short = float(min(crop.shape[:2])) * .25
    if board_corners is not None and len(board_corners) == 4:
        board_source = np.asarray(board_corners, np.float32) * np.asarray([frame.shape[1], frame.shape[0]], np.float32)
        board_edges = [float(np.linalg.norm(board_source[(index + 1) % 4] - board_source[index])) for index in range(4)]
        board_long, board_short = max(board_edges), max(4.0, min(board_edges))
    foul_source = None
    if foul_line is not None and len(foul_line) == 2:
        foul_source = np.asarray(foul_line, dtype=np.float32) * np.asarray([frame.shape[1], frame.shape[0]], dtype=np.float32)
    scored: list[tuple[float, np.ndarray]] = []
    candidate_debug: list[tuple[tuple[float, float], ...]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        # Reject isolated lace highlights, tape corners, and codec specks. At
        # normal board-review scale a usable contact region occupies more than
        # two thousandths of the expanded board crop.
        if area < max(20.0, crop_area * .002) or area > crop_area * .28:
            continue
        left, top, width, height = cv2.boundingRect(contour)
        aspect = width / max(1.0, float(height))
        if aspect < .18 or aspect > 8.0:
            continue
        rect = cv2.minAreaRect(contour)
        rect_long = max(float(rect[1][0]), float(rect[1][1]))
        rect_short = max(1.0, min(float(rect[1][0]), float(rect[1][1])))
        axis_aspect = rect_long / rect_short
        if axis_aspect > 9.0 or rect_short < 3.0:
            continue
        contour_mask = np.zeros(mask.shape, dtype=np.uint8)
        cv2.drawContours(contour_mask, [contour], -1, 255, thickness=-1)
        pixels = contour_mask > 0
        edge_density = float(np.count_nonzero(edges & pixels)) / max(1.0, area)
        non_shadow = 1.0 - float(np.count_nonzero(shadow & pixels)) / max(1.0, float(np.count_nonzero(pixels)))
        if non_shadow < .35 and edge_density < .12:
            continue
        global_contour = contour.reshape((-1, 2)).astype(np.float32) + np.asarray([x0, y0], np.float32)
        debug_outline = cv2.approxPolyDP(global_contour.reshape((-1, 1, 2)), max(1.0, .01 * cv2.arcLength(global_contour.reshape((-1, 1, 2)), True)), True).reshape((-1, 2))
        candidate_debug.append(tuple((float(x), float(y)) for x, y in debug_outline))
        hull_area = max(area, float(cv2.contourArea(cv2.convexHull(contour))))
        solidity = area / max(1.0, hull_area)
        compactness = area / max(1.0, float(width * height))
        shape_score = math.exp(-abs(math.log(max(1.0, axis_aspect) / 2.4)) * .72)
        relative_length = rect_long / max(8.0, board_long)
        completeness = min(1.0, relative_length / .16)
        if relative_length > .72:
            completeness *= max(.0, 1.0 - (relative_length - .72) / .40)
        line_proximity = 1.0
        if foul_source is not None:
            closest_line = min(_line_distance(point, foul_source) for point in global_contour[::max(1, len(global_contour) // 80)])
            line_proximity = math.exp(-closest_line / max(8.0, board_short * .65))
        board_proximity = 1.0
        if board_source is not None:
            board_contour = board_source.reshape((-1, 1, 2))
            closest_board = min(
                max(0.0, -float(cv2.pointPolygonTest(board_contour, (float(point[0]), float(point[1])), True)))
                for point in global_contour[::max(1, len(global_contour) // 80)]
            )
            board_proximity = math.exp(-closest_board / max(8.0, board_short * .85))
        pixels_count = max(1, int(np.count_nonzero(pixels)))
        candidate_skin = float(np.count_nonzero((skin_reject > 0) & pixels)) / pixels_count
        candidate_red = float(np.count_nonzero((((hsv[:, :, 0] <= 14) | (hsv[:, :, 0] >= 165)) & (hsv[:, :, 1] >= 60)) & pixels)) / pixels_count
        candidate_light = float(np.count_nonzero(((hsv[:, :, 1] < 45) & (hsv[:, :, 2] > 165)) & pixels)) / pixels_count
        board_marking_penalty = max(0.0, (candidate_light - .62) / .38) if axis_aspect > 3.8 and solidity > .82 else 0.0
        score = (
            .16 * min(1.0, edge_density / .11)
            + .11 * non_shadow
            + .09 * solidity
            + .09 * compactness
            + .18 * completeness
            + .15 * line_proximity
            + .14 * board_proximity
            + .08 * shape_score
            - .18 * candidate_skin
            - .14 * candidate_red
            - .18 * board_marking_penalty
        )
        # Calibration is used for board proximity and orientation, never as a
        # hard shoe-size gate. A close/far camera or non-standard board must not
        # make a complete visible shoe lose to a tiny toe fragment.
        scored.append((score, contour))
    if not scored:
        return None
    confidence, contour = max(scored, key=lambda item: item[0])
    perimeter = cv2.arcLength(contour, True)
    # Preserve the toe curvature: coarse simplification is particularly
    # damaging at the exact point used for judging.
    polygon = cv2.approxPolyDP(contour, max(.8, 0.006 * perimeter), True).reshape((-1, 2))
    if len(polygon) < 3:
        return None
    polygon = polygon.astype(np.float32)
    polygon[:, 0] += x0
    polygon[:, 1] += y0
    result = FootEstimate(
        tuple((float(x), float(y)) for x, y in polygon),
        max(0.0, min(1.0, confidence)),
        (float(x0), float(y0), float(x1), float(y1)),
        tuple(candidate_debug),
    )
    _LOGGER.info(
        "shoe_detection duration_ms=%.2f candidates=%d contour_points=%d confidence=%.3f",
        (time.perf_counter() - started) * 1000.0, len(candidate_debug), len(polygon), result.confidence,
    )
    return result


def _line_distance(point: np.ndarray, line: np.ndarray) -> float:
    start, end = line
    vector = end - start
    denominator = float(np.dot(vector, vector))
    if denominator <= 1e-9:
        return float(np.linalg.norm(point - start))
    projection = start + vector * float(np.dot(point - start, vector) / denominator)
    return float(np.linalg.norm(point - projection))


def _board_metric_transform(
    points: np.ndarray,
    foul_line: np.ndarray,
    length_cm: float,
    width_cm: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Map the square homography to physical axes selected by the foul line.

    The board's 120.1 cm axis is always parallel to the calibrated foul line;
    this remains true when the camera or clicked-corner order is rotated.
    """
    direction = foul_line[1] - foul_line[0]
    horizontal = abs(float(direction[0])) >= abs(float(direction[1]))
    if horizontal:
        scale = np.asarray([length_cm, width_cm], dtype=np.float32)
        return points * scale, foul_line * scale
    swapped = points[:, [1, 0]]
    swapped_line = foul_line[:, [1, 0]]
    scale = np.asarray([length_cm, width_cm], dtype=np.float32)
    return swapped * scale, swapped_line * scale


def project_points_to_board_cm(
    points_px: Sequence[Sequence[float]],
    calibration: ProjectionCalibration,
    frame_size: tuple[int, int],
) -> np.ndarray:
    source_calibration = calibration
    calibration = corrected_projection_calibration(source_calibration, frame_size)
    points_px = undistort_points_for_projection(points_px, frame_size, source_calibration)
    normalized = project_points_to_pad(points_px, calibration.board_corners, frame_size)
    foul_source = np.asarray(calibration.foul_line, dtype=np.float32) * np.asarray(frame_size, dtype=np.float32)
    foul_normalized = project_points_to_pad(foul_source, calibration.board_corners, frame_size)
    metric, _line = _board_metric_transform(
        normalized,
        foul_normalized,
        calibration.pad_length_cm or STANDARD_BOARD_LENGTH_CM,
        calibration.pad_width_cm or STANDARD_BOARD_WIDTH_CM,
    )
    return metric


def measurement_uncertainty_cm(
    calibration_error_cm: float,
    resolution_cm_per_px: float,
    segmentation_variation_cm: float,
    fit_variation_cm: float = 0.0,
) -> float:
    """Combine independent measurement error sources without false precision."""
    terms = (
        max(0.0, float(calibration_error_cm)),
        max(0.0, float(resolution_cm_per_px)) / math.sqrt(12.0),
        max(0.0, float(segmentation_variation_cm)),
        max(0.0, float(fit_variation_cm)),
    )
    return max(0.1, math.sqrt(sum(value * value for value in terms)))


def _signed_distance_details(
    polygon_cm: np.ndarray,
    line_cm: np.ndarray,
    legal_side_flipped: bool,
    board_size_cm: tuple[float, float] = (STANDARD_BOARD_LENGTH_CM, STANDARD_BOARD_WIDTH_CM),
) -> tuple[float, np.ndarray, np.ndarray]:
    start, end = line_cm
    vector = end - start
    length = float(np.linalg.norm(vector))
    if length <= 1e-7:
        raise ValueError("Foul-line endpoints must be different")
    # The half of the calibrated board containing its physical centre is legal.
    board_centre = np.asarray([board_size_cm[0] / 2.0, board_size_cm[1] / 2.0], dtype=np.float32)
    cross_centre = float(vector[0] * (board_centre[1] - start[1]) - vector[1] * (board_centre[0] - start[0]))
    legal_sign = 1.0 if cross_centre >= 0.0 else -1.0
    if legal_side_flipped:
        legal_sign *= -1.0
    relative = polygon_cm - start
    signed = legal_sign * (vector[0] * relative[:, 1] - vector[1] * relative[:, 0]) / length
    index = int(np.argmin(signed))
    shoe = polygon_cm[index]
    line_point = start + vector * float(np.dot(shoe - start, vector) / max(1e-9, np.dot(vector, vector)))
    return float(signed[index]), shoe, line_point


def measure_projected_foot(
    polygon_px: Sequence[Sequence[float]],
    calibration: ProjectionCalibration,
    frame_size: tuple[int, int],
    confidence: float = 0.65,
    segmentation_variation_cm: float | None = None,
    fit_variation_cm: float = 0.0,
) -> ProjectionMeasurement:
    source_calibration = calibration
    calibration = corrected_projection_calibration(source_calibration, frame_size)
    polygon_px = undistort_points_for_projection(polygon_px, frame_size, source_calibration)
    polygon = project_points_to_pad(polygon_px, calibration.board_corners, frame_size)
    foul_line_source_px = np.asarray(calibration.foul_line, dtype=np.float32) * np.asarray(frame_size, dtype=np.float32)
    foul_line = project_points_to_pad(foul_line_source_px, calibration.board_corners, frame_size)
    length_cm = calibration.pad_length_cm or STANDARD_BOARD_LENGTH_CM
    width_cm = calibration.pad_width_cm or STANDARD_BOARD_WIDTH_CM
    scaled_polygon, scaled_line = _board_metric_transform(polygon, foul_line, length_cm, width_cm)
    signed, shoe_point, line_point = _signed_distance_details(scaled_polygon, scaled_line, calibration.legal_side_flipped, (length_cm, width_cm))
    # Estimate local image resolution in the judging direction around the
    # nearest sole point. Calibration/click and segmentation errors are kept
    # separate so accepted multi-frame fits can add their observed variation.
    source = np.asarray(polygon_px, dtype=np.float32)
    nearest_index = int(np.argmin(np.linalg.norm(scaled_polygon - shoe_point, axis=1)))
    probe = np.vstack((source[nearest_index], source[nearest_index] + (1.0, 0.0), source[nearest_index] + (0.0, 1.0)))
    probe_cm = project_points_to_board_cm(probe, calibration, frame_size)
    resolution = max(float(np.linalg.norm(probe_cm[1] - probe_cm[0])), float(np.linalg.norm(probe_cm[2] - probe_cm[0])))
    calibration_error = resolution * 2.0
    segmentation = resolution * (0.8 + 1.7 * (1.0 - max(0.0, min(1.0, confidence)))) if segmentation_variation_cm is None else segmentation_variation_cm
    uncertainty = measurement_uncertainty_cm(calibration_error, resolution, segmentation, fit_variation_cm)
    status = "touching" if abs(signed) <= uncertainty else ("clear" if signed > 0 else "over")
    return ProjectionMeasurement(
        tuple((float(x), float(y)) for x, y in polygon),
        signed,
        uncertainty,
        status,
        (float(shoe_point[0]), float(shoe_point[1])),
        (float(line_point[0]), float(line_point[1])),
        max(0.0, min(1.0, float(confidence))),
    )


def estimated_footprint(
    polygon: Sequence[Sequence[float]],
    calibration: ProjectionCalibration,
) -> tuple[tuple[float, float], ...]:
    """Build an optional planar shoe-width envelope around the projected span."""
    points = np.asarray(polygon, dtype=np.float32)
    if points.shape[0] < 3 or calibration.shoe_width_cm <= 0 or calibration.pad_width_cm <= 0:
        return tuple((float(x), float(y)) for x, y in points)
    half_width = calibration.shoe_width_cm / calibration.pad_width_cm / 2.0
    x0, x1 = float(points[:, 0].min()), float(points[:, 0].max())
    centre_y = float(points[:, 1].mean())
    y0, y1 = max(0.0, centre_y - half_width), min(1.0, centre_y + half_width)
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def calibration_matches(
    calibration: ProjectionCalibration | None,
    camera_signature: str,
    frame_size: tuple[int, int],
) -> bool:
    return bool(
        calibration
        and len(calibration.board_corners) == 4
        and len(calibration.foul_line) == 2
        and calibration.camera_signature == camera_signature
        and calibration.reference_width == int(frame_size[0])
        and calibration.reference_height == int(frame_size[1])
    )


def _hex_bgr(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    try:
        value = value.lstrip("#")
        red, green, blue = (int(value[index:index + 2], 16) for index in (0, 2, 4))
        return blue, green, red
    except (ValueError, TypeError):
        return fallback


def render_board_projection_image(
    frame: np.ndarray,
    calibration: ProjectionCalibration,
    shoe_points_px: Sequence[Sequence[float]],
    confidence: float,
    output_size: tuple[int, int] = (720, 330),
    show_overlays: bool = True,
) -> np.ndarray:
    """Render the evidence-first flattened board without touching Tk."""
    canvas_width, canvas_height = output_size
    frame_size = (frame.shape[1], frame.shape[0])
    source_calibration = calibration
    calibration = corrected_projection_calibration(source_calibration, frame_size)
    shoe_points_px = undistort_points_for_projection(shoe_points_px, frame_size, source_calibration)
    has_shoe = len(shoe_points_px) >= 3
    length = calibration.pad_length_cm or STANDARD_BOARD_LENGTH_CM
    width = calibration.pad_width_cm or STANDARD_BOARD_WIDTH_CM
    ratio = max(1.5, min(7.0, length / width))
    pad_width, pad_height = 900, max(190, min(360, int(900 / ratio)))
    homography = compute_physical_pad_homography(calibration.board_corners, calibration.foul_line, frame_size, (pad_width, pad_height))
    corrected = undistort_frame_for_projection(frame, source_calibration)
    pad = cv2.warpPerspective(corrected, homography, (pad_width, pad_height))
    valid = cv2.warpPerspective(
        np.full(corrected.shape[:2], 255, dtype=np.uint8),
        homography,
        (pad_width, pad_height),
        flags=cv2.INTER_NEAREST,
    )
    # A malformed/partially stale calibration can map every destination pixel
    # outside the source image. Keep the evidence view useful instead of
    # presenting a completely black result; the operator can still correct the
    # four board points in the source view.
    valid_fraction = float(np.count_nonzero(valid)) / float(max(1, valid.size))
    visible_fraction = float(np.count_nonzero(pad)) / float(max(1, pad.size))
    if pad.size and (valid_fraction < 0.45 or visible_fraction < 0.02):
        source = np.asarray(calibration.board_corners, np.float32) * np.asarray(frame_size, np.float32)
        x0, y0 = np.floor(source.min(axis=0)).astype(int)
        x1, y1 = np.ceil(source.max(axis=0)).astype(int)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
        crop = corrected[y0:y1, x0:x1]
        if crop.size:
            pad = cv2.resize(crop, (pad_width, pad_height), interpolation=cv2.INTER_AREA)
    canvas = np.full((canvas_height, canvas_width, 3), (18, 21, 26), dtype=np.uint8)
    left, right, top = (24, canvas_width - 24, 46) if has_shoe else (12, canvas_width - 12, 12)
    bottom_margin = 42 if has_shoe else 12
    bottom = min(canvas_height - bottom_margin, top + int((right - left) / ratio))
    shown = cv2.resize(pad, (right - left, max(1, bottom - top)), interpolation=cv2.INTER_AREA)
    canvas[top:bottom, left:right] = shown[:bottom - top, :right - left]
    normalized_foul = project_points_to_pad(
        np.asarray(calibration.foul_line, np.float32) * np.asarray(frame_size, np.float32),
        calibration.board_corners,
        frame_size,
    )
    horizontal = abs(float(normalized_foul[1, 0] - normalized_foul[0, 0])) >= abs(float(normalized_foul[1, 1] - normalized_foul[0, 1]))
    def physical(points: Sequence[Sequence[float]]) -> np.ndarray:
        values = np.asarray(points, np.float32)
        return values if horizontal else values[:, [1, 0]]
    def map_points(points: Sequence[Sequence[float]]) -> np.ndarray:
        values = physical(points)
        result = np.empty_like(values)
        result[:, 0] = left + values[:, 0] * (right - left - 1)
        result[:, 1] = top + values[:, 1] * (bottom - top - 1)
        return np.rint(result).astype(np.int32)
    measurement = None
    foot = None
    if has_shoe:
        measurement = measure_projected_foot(shoe_points_px, calibration, frame_size, confidence=confidence)
        foot = map_points(measurement.polygon)
    foul = map_points(normalized_foul)
    if show_overlays and foot is not None:
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [foot], (80, 190, 235))
        cv2.addWeighted(overlay, .36, canvas, .64, 0, canvas)
        cv2.polylines(canvas, [foot], True, (80, 220, 170), 3, cv2.LINE_AA)
        cv2.line(canvas, tuple(foul[0]), tuple(foul[1]), (100, 100, 255), 4, cv2.LINE_AA)
        cv2.rectangle(canvas, (left, top), (right - 1, bottom - 1), (220, 220, 220), 2)
    elif show_overlays:
        cv2.line(canvas, tuple(foul[0]), tuple(foul[1]), (100, 100, 255), 4, cv2.LINE_AA)
        cv2.rectangle(canvas, (left, top), (right - 1, bottom - 1), (220, 220, 220), 2)
    if measurement is None:
        # The shoe-less fallback has no title or verdict footer. Return only
        # the rectified board pixels so the former label area cannot survive as
        # an empty dark/brown frame around the useful image.
        return np.ascontiguousarray(canvas[top:bottom, left:right])
    if measurement is not None:
        cv2.putText(canvas, "BOARD PROJECTION", (18, 26), cv2.FONT_HERSHEY_SIMPLEX, .58, (230, 234, 240), 2, cv2.LINE_AA)
        verdict = projection_verdict_text(measurement.status)
        verdict_color = projection_verdict_color(measurement.status)
        cv2.putText(canvas, verdict, (18, canvas_height - 13), cv2.FONT_HERSHEY_SIMPLEX, .72, verdict_color, 2, cv2.LINE_AA)
    return canvas


class _LegacyTopViewProjectionWindow:
    """Fast, modeless review surface for one frozen attempt."""

    def __init__(
        self,
        master: tk.Misc,
        palette: dict[str, str],
        language: str,
        attempt_id: int,
        packets: Sequence[FramePacket],
        target_timestamp_ns: int,
        roi: Sequence[float],
        calibration: ProjectionCalibration | None,
        calibration_warning: str,
        camera_signature: str,
        on_calibration_saved: Callable[[ProjectionCalibration], None],
        on_confirm: Callable[[int], None],
        on_close: Callable[[], None],
        candidates: Sequence[ProjectionCandidate] | None = None,
        reference_frames: Sequence[np.ndarray] | None = None,
    ) -> None:
        self.master = master
        self.palette = palette
        self.language = language
        self.attempt_id = attempt_id
        self.packets = list(packets)
        self.roi = tuple(roi)
        self.target_timestamp_ns = int(target_timestamp_ns)
        self.camera_signature = camera_signature
        self.on_calibration_saved = on_calibration_saved
        self.on_confirm = on_confirm
        self.on_close = on_close
        self._closed = False
        self._calibrating = False
        self._editing = False
        self._drag_index: int | None = None
        self._board_points: list[tuple[float, float]] = []
        self._foul_points: list[tuple[float, float]] = []
        self._foot_points: list[tuple[float, float]] = []
        self._foot_confidence = 0.0
        self._source_bounds = (0.0, 0.0, 1.0, 1.0)
        self._source_frame_size = (0, 0)
        self._source_photo: ImageTk.PhotoImage | None = None
        self._projection_photo: ImageTk.PhotoImage | None = None
        self._reconstruction_result: ReconstructionResult | None = None
        self._reconstruction_generation = 0
        self._reconstruction_cancel: Event | None = None
        self._reconstruction_queue: Queue[tuple[int, str, object]] = Queue()
        self._active_view: str | None = None
        self.calibration = calibration
        self.candidates = list(candidates) if candidates is not None else rank_projection_candidates(self.packets, target_timestamp_ns, self.roi)
        self.reference_frames = [frame for frame in (reference_frames or ()) if frame is not None]
        self._candidate_estimates: dict[int, FootEstimate | None] = {}
        if self.calibration is not None:
            self.candidates = self._filter_candidates_with_shoes(self.candidates)
        self.current_candidate = 0
        self.status_var = tk.StringVar(value="")
        self.instruction_var = tk.StringVar(value="")

        self.window = tk.Toplevel(master)
        center_popup(self.window)
        self.window.title(self._text("Top-view projection", "Projekce shora"))
        self.window.geometry("1180x760")
        self.window.minsize(900, 620)
        self.window.configure(bg=palette["bg"])
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(3, weight=1)

        header = ttk.Frame(self.window, style="Panel.TFrame", padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=self._text("TOP-VIEW PROJECTION", "PROJEKCE SHORA"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text=self._text("Decision support only — the original camera frame remains authoritative.", "Pouze podpůrné zobrazení — původní snímek kamery zůstává rozhodující."),
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        self.candidate_strip = ttk.Frame(self.window, style="Toolbar.TFrame", padding=(10, 7))
        self.candidate_strip.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 0))
        self.candidate_strip.columnconfigure(0, weight=1)
        thumbnail_canvas = tk.Canvas(self.candidate_strip, height=110, bg=palette["surface2"], highlightthickness=0)
        thumbnail_canvas.grid(row=0, column=0, sticky="ew")
        thumbnail_scroll = ttk.Scrollbar(self.candidate_strip, orient="horizontal", command=thumbnail_canvas.xview)
        thumbnail_scroll.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        thumbnail_canvas.configure(xscrollcommand=thumbnail_scroll.set)
        candidate_inner = ttk.Frame(thumbnail_canvas, style="Toolbar.TFrame")
        thumbnail_canvas.create_window((0, 0), window=candidate_inner, anchor="nw")
        candidate_inner.bind("<Configure>", lambda _event: thumbnail_canvas.configure(scrollregion=thumbnail_canvas.bbox("all")))
        self._thumbnail_photos: list[ImageTk.PhotoImage] = []
        self._thumbnail_labels: list[tk.Label] = []
        for index, candidate in enumerate(self.candidates[:7]):
            thumbnail = tk.Label(candidate_inner, bg=palette["surface2"], bd=2, relief="flat", cursor="hand2")
            thumbnail.pack(side="left", padx=3)
            thumbnail.bind("<Button-1>", lambda _event, index=index: self._select_candidate(index))
            photo = self._photo(candidate.frame_bgr, (160, 100))
            thumbnail.configure(image=photo)
            self._thumbnail_photos.append(photo)
            self._thumbnail_labels.append(thumbnail)
        if not self.candidates:
            ttk.Label(candidate_inner, text=self._text("No usable frames were found.", "Nebyly nalezeny použitelné snímky."), style="Warning.TLabel").pack(anchor="w")

        guide = ttk.Frame(self.window, style="Panel.TFrame", padding=(14, 9))
        guide.grid(row=2, column=0, sticky="ew", padx=10, pady=(8, 0))
        ttk.Label(guide, textvariable=self.instruction_var, style="Title.TLabel", anchor="w").pack(fill="x")
        self.view_choice = ttk.Frame(guide, style="Panel.TFrame")
        self.view_choice.pack(fill="x", pady=(7, 0))
        ttk.Label(self.view_choice, text=self._text("Choose the view to compute first:", "Nejprve zvolte pohled k výpočtu:"), style="Muted.TLabel").pack(side="left")
        ttk.Button(self.view_choice, text=self._text("Board projection", "Projekce prkna"), command=lambda: self._choose_view("projection")).pack(side="left", padx=(12, 4))
        ttk.Button(self.view_choice, text=self._text("Overhead shoe", "Bota shora"), command=lambda: self._choose_view("overhead")).pack(side="left")

        body = ttk.Panedwindow(self.window, orient="horizontal")
        body.grid(row=3, column=0, sticky="nsew", padx=10, pady=10)
        source_frame = ttk.Frame(body, style="Panel.TFrame", padding=6)
        projection_frame = ttk.Frame(body, style="Panel.TFrame", padding=6)
        body.add(source_frame, weight=1)
        body.add(projection_frame, weight=1)
        source_frame.rowconfigure(0, weight=1); source_frame.columnconfigure(0, weight=1)
        projection_frame.rowconfigure(2, weight=1); projection_frame.columnconfigure(0, weight=1)
        self.source_canvas = tk.Canvas(source_frame, bg=palette["video"], highlightthickness=1, highlightbackground=palette["border"])
        self.source_canvas.grid(row=0, column=0, sticky="nsew")
        view_bar = ttk.Frame(projection_frame, style="Panel.TFrame")
        view_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.projection_view_button = ttk.Button(view_bar, text=self._text("Board projection", "Projekce prkna"), command=lambda: self._show_view("projection"))
        self.projection_view_button.pack(side="left")
        self.overhead_view_button = ttk.Button(view_bar, text=self._text("Overhead shoe", "Bota shora"), command=lambda: self._show_view("overhead"))
        self.overhead_view_button.pack(side="left", padx=(5, 0))
        progress_frame = ttk.Frame(projection_frame, style="Panel.TFrame")
        progress_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        progress_frame.columnconfigure(0, weight=1)
        self.reconstruction_stage_var = tk.StringVar(value="")
        ttk.Label(progress_frame, textvariable=self.reconstruction_stage_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.reconstruction_progress = ttk.Progressbar(progress_frame, orient="horizontal", mode="determinate", maximum=100, value=0, style="Modal.Horizontal.TProgressbar")
        self.reconstruction_progress.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.projection_canvas = tk.Canvas(projection_frame, bg=palette["video"], highlightthickness=1, highlightbackground=palette["border"])
        self.projection_canvas.grid(row=2, column=0, sticky="nsew")
        bind_resize_only(self.source_canvas, lambda _event: self._refresh_source())
        bind_resize_only(self.projection_canvas, lambda _event: self._render_projection())
        self.source_canvas.bind("<ButtonPress-1>", self._source_press)
        self.source_canvas.bind("<B1-Motion>", self._source_drag)
        self.source_canvas.bind("<ButtonRelease-1>", self._source_release)
        self.source_canvas.bind("<ButtonPress-3>", self._source_remove_point)
        self.source_canvas.bind("<Motion>", self._hover_zoom)
        self.source_canvas.bind("<Leave>", lambda _event: self.source_canvas.delete("zoom"))

        footer = ttk.Frame(self.window, style="Toolbar.TFrame", padding=(10, 7))
        footer.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel", anchor="w").grid(row=0, column=0, sticky="ew")
        ttk.Label(
            footer,
            text=self._text("Scale is automatic for the 120.1 × 34 cm board.", "Měřítko je automatické pro prkno 120,1 × 34 cm."),
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(7, 0))
        actions = ttk.Frame(footer, style="Toolbar.TFrame")
        actions.grid(row=1, column=1, sticky="e", pady=(7, 0))
        self.calibrate_button = ttk.Button(actions, text=self._text("Set up board", "Nastavit prkno"), command=self._start_calibration)
        self.calibrate_button.pack(side="left", padx=(0, 6))
        self.find_edges_button = ttk.Button(actions, text=self._text("Find board edges", "Najít hrany prkna"), command=self._auto_find_board_edges)
        self.find_edges_button.pack(side="left", padx=(0, 6))
        self.flip_side_button = ttk.Button(actions, text=self._text("Flip legal side", "Obrátit platnou stranu"), command=self._flip_legal_side)
        self.flip_side_button.pack(side="left", padx=(0, 6))
        self.estimate_button = ttk.Button(actions, text=self._text("Estimate foot", "Odhadnout botu"), command=self._estimate_foot)
        self.estimate_button.pack(side="left", padx=(0, 6))
        self.edit_button = ttk.Button(actions, text=self._text("Edit outline", "Upravit obrys"), command=self._toggle_editing)
        self.edit_button.pack(side="left", padx=(0, 6))
        self.confirm_button = ttk.Button(actions, text=self._text("Confirm projection", "Potvrdit projekci"), style="Primary.TButton", command=self._confirm)
        self.confirm_button.pack(side="left", padx=(0, 6))
        ttk.Button(actions, text=self._text("Cancel", "Zrušit"), command=self.close).pack(side="left")

        self.window.update_idletasks()
        if calibration_warning:
            self.status_var.set(self._text("The camera changed. Set up the board again.", "Kamera se změnila. Nastavte prkno znovu."))
        elif self.calibration is None:
            self.status_var.set(self._text("No board setup saved for this camera.", "Pro tuto kameru není uloženo nastavení prkna."))
        elif self.candidates:
            self.status_var.set(self._text("Board ready.", "Prkno je připravené."))
        self._update_instruction()
        self.candidate_strip.grid_remove()
        self._update_buttons()
        self.window.after(40, self._poll_reconstruction)

    def _text(self, english: str, czech: str) -> str:
        return czech if self.language == "cs" else english

    @staticmethod
    def _display_frame(frame: np.ndarray) -> np.ndarray:
        """Return a contiguous uint8 BGR image that Tk/Pillow can display safely."""
        shown = np.asarray(frame)
        if shown.ndim == 2:
            shown = cv2.cvtColor(shown, cv2.COLOR_GRAY2BGR)
        elif shown.ndim == 3 and shown.shape[2] == 4:
            shown = cv2.cvtColor(shown, cv2.COLOR_BGRA2BGR)
        elif shown.ndim != 3 or shown.shape[2] != 3:
            raise ValueError(f"Unsupported projection image shape: {shown.shape}")
        if shown.dtype != np.uint8:
            shown = np.nan_to_num(shown, nan=0.0, posinf=255.0, neginf=0.0)
            shown = np.clip(shown, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(shown)

    @staticmethod
    def _photo(frame: np.ndarray, size: tuple[int, int]) -> ImageTk.PhotoImage:
        frame = TopViewProjectionWindow._display_frame(frame)
        height, width = frame.shape[:2]
        scale = min(size[0] / max(1, width), size[1] / max(1, height))
        resized = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        return ImageTk.PhotoImage(Image.fromarray(rgb))

    def _current(self) -> ProjectionCandidate | None:
        return self.candidates[self.current_candidate] if self.candidates else None

    def _choose_view(self, view: str) -> None:
        self._active_view = "overhead" if view == "overhead" else "projection"
        self.view_choice.pack_forget()
        self.candidate_strip.grid()
        self.status_var.set(self._text("Preparing candidate frames...", "Připravuji snímky..."))
        if self.candidates:
            initial = min(range(len(self.candidates)), key=lambda index: abs(self.candidates[index].timestamp_ns - self.target_timestamp_ns))
            self._select_candidate(initial)
        else:
            self.instruction_var.set(self._text("No usable frame contains a shoe.", "Žádný použitelný snímek neobsahuje botu."))
            self._update_buttons()

    def _filter_candidates_with_shoes(self, candidates: Sequence[ProjectionCandidate]) -> list[ProjectionCandidate]:
        if not candidates or self.calibration is None:
            return list(candidates)
        kept: list[ProjectionCandidate] = []
        refs = list(self.reference_frames) or [item.frame_bgr for item in candidates[:7]]
        for item in candidates[:7]:
            other_refs = [frame for frame in refs if frame is not item.frame_bgr and frame.shape == item.frame_bgr.shape][:6]
            estimate = estimate_foot_polygon(item.frame_bgr, other_refs, self.roi, self.calibration.board_corners, self.calibration.foul_line)
            self._candidate_estimates[item.frame_index] = estimate
            if estimate is not None and estimate.confidence >= .28:
                kept.append(item)
        return kept

    def _show_view(self, view: str) -> None:
        self._active_view = "overhead" if view == "overhead" else "projection"
        self._render_projection()

    def _cancel_reconstruction(self) -> None:
        if self._reconstruction_cancel is not None:
            self._reconstruction_cancel.set()
        self._reconstruction_cancel = None

    def _start_reconstruction(self) -> None:
        candidate = self._current()
        if self._closed or candidate is None or self.calibration is None or len(self._foot_points) < 3:
            return
        self._cancel_reconstruction()
        self._reconstruction_generation += 1
        generation = self._reconstruction_generation
        cancel = Event()
        self._reconstruction_cancel = cancel
        self._reconstruction_result = None
        self.reconstruction_progress.configure(value=0)
        self.reconstruction_stage_var.set(self._text("Preparing frames…", "Připravuji snímky…"))
        selected_frame = candidate.frame_bgr.copy()
        outline = tuple(self._foot_points)
        # Sole-edge consensus is deliberately local to the judge-selected
        # frame: one neighbour on either side, and never farther than 300 ms.
        observations = tuple(
            (item.frame_index, item.frame_bgr)
            for item in self.candidates
            if abs(item.frame_index - candidate.frame_index) <= 1
            and abs(item.timestamp_ns - candidate.timestamp_ns) <= 300_000_000
        )
        references = tuple(self.reference_frames)
        calibration = self.calibration

        def worker() -> None:
            def report(stage: str, value: int) -> None:
                self._reconstruction_queue.put((generation, "progress", (stage, value)))
            try:
                result = reconstruct_shoe_overhead(
                    selected_frame, outline, observations, references, calibration,
                    time_limit_seconds=5.0, cancel=cancel, progress=report,
                )
                self._reconstruction_queue.put((generation, "result", result))
            except ReconstructionCancelled:
                self._reconstruction_queue.put((generation, "cancelled", None))
            except ReconstructionTimedOut:
                self._reconstruction_queue.put((generation, "timeout", None))
            except (ValueError, cv2.error) as exc:
                self._reconstruction_queue.put((generation, "unreliable", str(exc)))
            except Exception as exc:
                self._reconstruction_queue.put((generation, "unreliable", f"{type(exc).__name__}: {exc}"))

        Thread(target=worker, name=f"shoe-reconstruction-{self.attempt_id}-{generation}", daemon=True).start()

    def _poll_reconstruction(self) -> None:
        if self._closed:
            return
        labels = {
            "preparing_frames": self._text("Preparing frames…", "Připravuji snímky…"),
            "isolating_shoe": self._text("Isolating shoe…", "Odděluji botu…"),
            "fitting_model": self._text("Fitting model…", "Přizpůsobuji model…"),
            "rendering": self._text("Rendering…", "Vykresluji…"),
            "complete": self._text("Overhead shoe ready.", "Pohled na botu shora je připraven."),
        }
        try:
            while True:
                generation, kind, payload = self._reconstruction_queue.get_nowait()
                if generation != self._reconstruction_generation:
                    continue
                if kind == "progress":
                    stage, value = payload
                    self.reconstruction_stage_var.set(labels.get(str(stage), str(stage)))
                    self.reconstruction_progress.configure(value=max(float(self.reconstruction_progress["value"]), float(value)))
                elif kind == "result":
                    self._reconstruction_result = payload
                    self.reconstruction_stage_var.set(labels["complete"])
                    self.reconstruction_progress.configure(value=100)
                    self._render_projection()
                elif kind == "timeout":
                    self.reconstruction_stage_var.set(self._text("3D fit timed out; board projection remains available.", "3D výpočet vypršel; projekce prkna zůstává dostupná."))
                elif kind == "unreliable":
                    self.reconstruction_stage_var.set(self._text("3D fit was not reliable; board projection remains available.", "3D výsledek nebyl spolehlivý; projekce prkna zůstává dostupná."))
        except Empty:
            pass
        if not self._closed:
            self.window.after(40, self._poll_reconstruction)

    def _select_candidate(self, index: int) -> None:
        if not self.candidates:
            return
        if self._calibrating:
            self.status_var.set(self._text("Finish the board setup first.", "Nejprve dokončete nastavení prkna."))
            return
        self._cancel_reconstruction()
        self._reconstruction_generation += 1
        self._reconstruction_result = None
        self.current_candidate = max(0, min(len(self.candidates) - 1, int(index)))
        for candidate_index, thumbnail in enumerate(self._thumbnail_labels):
            thumbnail.configure(relief="solid" if candidate_index == self.current_candidate else "flat", highlightbackground=self.palette["accent"] if candidate_index == self.current_candidate else self.palette["surface2"])
        self._editing = False
        self._foot_points = []
        candidate = self._current()
        if self.calibration is not None and candidate is not None:
            height, width = candidate.frame_bgr.shape[:2]
            self._board_points = [(x * width, y * height) for x, y in self.calibration.board_corners]
            self._foul_points = [(x * width, y * height) for x, y in self.calibration.foul_line]
        self._refresh_source()
        if self.calibration is not None:
            self._estimate_foot()
        else:
            self._update_buttons()
        self._update_instruction()

    def _refresh_source(self) -> None:
        candidate = self._current()
        self.source_canvas.delete("overlay")
        if candidate is None:
            self.source_canvas.delete("source")
            self._update_buttons()
            return
        frame = candidate.frame_bgr
        height, width = frame.shape[:2]
        canvas_width = max(200, self.source_canvas.winfo_width())
        canvas_height = max(160, self.source_canvas.winfo_height())
        scale = min((canvas_width - 12) / width, (canvas_height - 12) / height)
        render_width, render_height = max(1, int(width * scale)), max(1, int(height * scale))
        left = (canvas_width - render_width) / 2
        top = (canvas_height - render_height) / 2
        resized = cv2.resize(frame, (render_width, render_height), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        self._source_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)))
        self.source_canvas.delete("source")
        self.source_canvas.create_image(left, top, image=self._source_photo, anchor="nw", tags="source")
        self._source_bounds = (left, top, left + render_width, top + render_height)
        self._source_frame_size = (width, height)
        self._draw_source_overlay()
        self._update_buttons()

    def _frame_to_canvas(self, point: Sequence[float]) -> tuple[float, float]:
        left, top, right, bottom = self._source_bounds
        width, height = self._source_frame_size
        return left + float(point[0]) / max(1, width) * (right - left), top + float(point[1]) / max(1, height) * (bottom - top)

    def _canvas_to_frame(self, x: float, y: float) -> tuple[float, float] | None:
        left, top, right, bottom = self._source_bounds
        width, height = self._source_frame_size
        if not (left <= x <= right and top <= y <= bottom):
            return None
        return ((x - left) / max(1.0, right - left) * width, (y - top) / max(1.0, bottom - top) * height)

    def _draw_source_overlay(self) -> None:
        self.source_canvas.delete("overlay")
        for points, color, label in (
            (self._board_points, "#f5bd4f", "PAD"),
            (self._foul_points, "#ff6675", "FOUL LINE"),
            (self._foot_points, "#70d6a5", "FOOT ESTIMATE"),
        ):
            if len(points) >= 2:
                canvas_points = [coord for point in points for coord in self._frame_to_canvas(point)]
                if label == "PAD" and len(points) == 4:
                    self.source_canvas.create_polygon(*canvas_points, outline=color, fill="", width=2, tags="overlay")
                elif label == "FOOT ESTIMATE" and len(points) >= 3:
                    self.source_canvas.create_polygon(*canvas_points, outline=color, fill="", width=2, tags="overlay")
                elif label != "PAD":
                    self.source_canvas.create_line(*canvas_points, fill=color, width=2, tags="overlay")
            for index, point in enumerate(points):
                x, y = self._frame_to_canvas(point)
                self.source_canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill=color, outline="#111722", tags="overlay")
                self.source_canvas.create_text(x + 9, y - 9, text=str(index + 1), fill=color, anchor="sw", tags="overlay")
        candidate = self._current()
        if candidate:
            self.source_canvas.create_text(10, 10, text=f"FRAME {candidate.frame_index + 1}  |  {candidate.score:.0%} shortlist", fill=self.palette["text"], anchor="nw", tags="overlay")

    def _update_instruction(self) -> None:
        if self._calibrating and len(self._board_points) < 4:
            self.instruction_var.set(self._text(
                f"1 of 2  ·  Click the 4 board corners — any order ({len(self._board_points)}/4)",
                f"1 ze 2  ·  Klikněte na 4 rohy prkna — v libovolném pořadí ({len(self._board_points)}/4)",
            ))
        elif self._calibrating:
            self.instruction_var.set(self._text(
                f"2 of 2  ·  Click both ends of the foul line ({len(self._foul_points)}/2)",
                f"2 ze 2  ·  Klikněte na oba konce odrazové čáry ({len(self._foul_points)}/2)",
            ))
        elif self.calibration is None:
            self.instruction_var.set(self._text("Choose a frame, then select Set up board.", "Vyberte snímek a potom Nastavit prkno."))
        else:
            self.instruction_var.set(self._text("Choose the best frame. Adjust the green outline if needed.", "Vyberte nejlepší snímek. V případě potřeby upravte zelený obrys."))

    def _start_calibration(self) -> None:
        if self._active_view is None:
            self._choose_view("projection")
        self._cancel_reconstruction()
        self._reconstruction_generation += 1
        self._reconstruction_result = None
        self._calibrating = True
        self._editing = False
        self._board_points.clear(); self._foul_points.clear()
        self._foot_points.clear()
        self.status_var.set(self._text("Start with the four yellow board corners.", "Začněte čtyřmi žlutými rohy prkna."))
        self._update_instruction(); self._update_buttons(); self._draw_source_overlay(); self._render_projection()

    def _auto_find_board_edges(self) -> None:
        candidate = self._current()
        if candidate is None:
            return
        found = detect_board_corners(candidate.frame_bgr, self.roi)
        if found is None:
            self.status_var.set(self._text("Board edges could not be found; click the four corners manually.", "Hrany prkna nebyly nalezeny; klikněte na čtyři rohy ručně."))
            return
        self._board_points = list(found)
        self._foul_points.clear()
        self._calibrating = True
        self.status_var.set(self._text("Board edges found. Correct any corner, then mark the foul line.", "Hrany prkna nalezeny. Opravte rohy a potom označte odrazovou čáru."))
        self._update_instruction(); self._draw_source_overlay(); self._update_buttons()

    def _finish_calibration(self) -> None:
        if len(self._board_points) != 4 or len(self._foul_points) != 2:
            self.status_var.set(self._text("Four pad corners and two foul-line points are required.", "Jsou nutné čtyři rohy prkna a dva body odrazové čáry."))
            return
        try:
            calibration = create_projection_calibration(
                self._board_points,
                self._foul_points,
                self._source_frame_size,
                self.camera_signature,
                self.calibration,
            )
        except ValueError as exc:
            self.status_var.set(str(exc)); return
        self.calibration = calibration
        width, height = self._source_frame_size
        self._board_points = [(x * width, y * height) for x, y in calibration.board_corners]
        self._calibrating = False
        self.on_calibration_saved(calibration)
        self.status_var.set(self._text("Board ready. Estimating the foot…", "Prkno je připravené. Odhaduji botu…"))
        self._update_instruction()
        self._estimate_foot()

    def _estimate_foot(self) -> None:
        candidate = self._current()
        if candidate is None:
            return
        if self.calibration is None:
            self.status_var.set(self._text("Calibrate the pad first.", "Nejprve kalibrujte prkno.")); self._update_buttons(); return
        references = list(self.reference_frames)
        if not references:
            references.extend(
                other.frame_bgr
                for index, other in sorted(
                    enumerate(self.candidates),
                    key=lambda item: abs(item[1].timestamp_ns - candidate.timestamp_ns),
                    reverse=True,
                )
                if index != self.current_candidate
            )
        references = [reference for reference in references if reference.shape == candidate.frame_bgr.shape][:6]
        estimate = self._candidate_estimates.get(candidate.frame_index)
        if estimate is None and candidate.frame_index not in self._candidate_estimates:
            estimate = estimate_foot_polygon(
            candidate.frame_bgr,
            references,
            self.roi,
            self.calibration.board_corners,
            self.calibration.foul_line,
            )
        if estimate is None:
            self._foot_points = []
            self._foot_confidence = 0.0
            self.status_var.set(self._text("The foot could not be isolated. Use Edit outline to mark it manually.", "Botu se nepodařilo oddělit. Označte ji ručně přes Upravit obrys."))
        else:
            self._foot_points = list(estimate.polygon_px)
            self._foot_confidence = estimate.confidence
            self.status_var.set(self._text(f"Foot estimate ready — confidence {estimate.confidence:.0%}.", f"Odhad boty připraven — spolehlivost {estimate.confidence:.0%}."))
        self._draw_source_overlay(); self._render_projection(); self._update_buttons()
        if estimate is not None:
            self._start_reconstruction()

    def _toggle_editing(self) -> None:
        self._editing = not self._editing
        self.status_var.set(self._text("Drag points or click to add an outline point. Right-click removes one.", "Táhněte body nebo kliknutím přidejte bod obrysu. Pravé tlačítko bod odstraní.")) if self._editing else None
        self._update_buttons()

    def _source_press(self, event) -> str:
        point = self._canvas_to_frame(event.x, event.y)
        if point is None:
            return "break"
        if self._calibrating:
            if len(self._board_points) < 4:
                self._board_points.append(point)
                if len(self._board_points) == 4:
                    try:
                        self._board_points = [tuple(value) for value in order_board_corners(self._board_points)]
                        self.status_var.set(self._text("Now mark the red foul line.", "Nyní označte červenou odrazovou čáru."))
                    except ValueError as exc:
                        self._board_points.clear()
                        self.status_var.set(str(exc))
            elif len(self._foul_points) < 2:
                self._foul_points.append(point)
            self._update_instruction(); self._draw_source_overlay(); self._update_buttons()
            if len(self._board_points) == 4 and len(self._foul_points) == 2:
                self._finish_calibration()
            return "break"
        if self._editing:
            self._drag_index = next((index for index, existing in enumerate(self._foot_points) if math.hypot(existing[0] - point[0], existing[1] - point[1]) < 30), None)
            if self._drag_index is None and len(self._foot_points) < 16:
                # Insert on the nearest outline segment so clicking the line
                # refines the contour instead of making a disconnected tail.
                best_index, best_distance = None, float("inf")
                for index, start in enumerate(self._foot_points):
                    end = self._foot_points[(index + 1) % len(self._foot_points)]
                    ax, ay = start; bx, by = end; px, py = point
                    dx, dy = bx - ax, by - ay
                    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / max(1e-6, dx * dx + dy * dy)))
                    distance = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
                    if distance < best_distance:
                        best_index, best_distance = index, distance
                if best_index is not None and best_distance < 45:
                    self._foot_points.insert(best_index + 1, point)
                else:
                    self._foot_points.append(point)
                self._draw_source_overlay(); self._render_projection()
                if len(self._foot_points) >= 3:
                    self._start_reconstruction()
        return "break"

    def _hover_zoom(self, event) -> str:
        candidate = self._current()
        point = self._canvas_to_frame(event.x, event.y)
        if candidate is None or point is None:
            self.source_canvas.delete("zoom")
            return "break"
        frame = candidate.frame_bgr
        cx, cy = int(point[0]), int(point[1])
        crop_w, crop_h = max(40, frame.shape[1] // 8), max(30, frame.shape[0] // 8)
        x0, y0 = max(0, cx - crop_w // 2), max(0, cy - crop_h // 2)
        x1, y1 = min(frame.shape[1], x0 + crop_w), min(frame.shape[0], y0 + crop_h)
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return "break"
        zoom = cv2.resize(crop, (220, 140), interpolation=cv2.INTER_LINEAR)
        self._zoom_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(zoom, cv2.COLOR_BGR2RGB)))
        self.source_canvas.delete("zoom")
        self.source_canvas.create_rectangle(event.x - 18, event.y - 18, event.x + 18, event.y + 18, outline="#fff1a8", width=2, tags="zoom")
        px = min(max(110, event.x + 120), max(110, self.source_canvas.winfo_width() - 110))
        py = min(max(75, event.y + 90), max(75, self.source_canvas.winfo_height() - 75))
        self.source_canvas.create_image(px, py, image=self._zoom_photo, anchor="center", tags="zoom")
        return "break"

    def _source_drag(self, event) -> str:
        if self._editing and self._drag_index is not None:
            point = self._canvas_to_frame(event.x, event.y)
            if point is not None:
                self._foot_points[self._drag_index] = point
                self._draw_source_overlay(); self._render_projection()
        return "break"

    def _source_release(self, _event) -> str:
        changed = self._editing and self._drag_index is not None
        self._drag_index = None
        if changed:
            self._start_reconstruction()
        return "break"

    def _source_remove_point(self, event) -> str:
        if self._calibrating:
            if self._foul_points:
                self._foul_points.pop()
            elif self._board_points:
                self._board_points.pop()
            self.status_var.set(self._text("Last point removed.", "Poslední bod byl odebrán."))
            self._update_instruction(); self._draw_source_overlay(); self._update_buttons()
            return "break"
        if not self._editing or not self._foot_points:
            return "break"
        point = self._canvas_to_frame(event.x, event.y)
        if point is not None:
            index = min(range(len(self._foot_points)), key=lambda candidate: math.hypot(self._foot_points[candidate][0] - point[0], self._foot_points[candidate][1] - point[1]))
            if math.hypot(self._foot_points[index][0] - point[0], self._foot_points[index][1] - point[1]) < 45:
                self._foot_points.pop(index); self._draw_source_overlay(); self._render_projection()
                if len(self._foot_points) >= 3:
                    self._start_reconstruction()
        return "break"

    def _flip_legal_side(self) -> None:
        if self.calibration is None:
            return
        self.calibration = replace(self.calibration, legal_side_flipped=not self.calibration.legal_side_flipped)
        self.on_calibration_saved(self.calibration)
        self._render_projection()
        self._start_reconstruction()

    def _open_camera_profile_wizard(self) -> None:
        dialog = tk.Toplevel(self.window)
        center_popup(dialog)
        dialog.title(self._text("Advanced camera profile", "Pokročilý profil kamery"))
        dialog.transient(self.window)
        dialog.configure(bg=self.palette["bg"])
        frame = ttk.Frame(dialog, style="Panel.TFrame", padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=self._text("Optional checkerboard camera profile", "Volitelný profil kamery se šachovnicí"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text=self._text(
            "Print the bundled board at 100% (25 mm squares), record at least three distinct views, then analyse those frames. Normal judging does not require this profile.",
            "Vytiskněte přiloženou desku na 100 % (čtverce 25 mm), zaznamenejte alespoň tři odlišné pohledy a potom snímky analyzujte. Běžné měření tento profil nevyžaduje.",
        ), style="Muted.TLabel", wraplength=520, justify="left").pack(anchor="w", pady=(6, 12))
        result_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=result_var, style="Status.TLabel", wraplength=520).pack(anchor="w", pady=(0, 10))
        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text=self._text("Open printable checkerboard", "Otevřít šachovnici k tisku"), command=lambda: os.startfile(str(checkerboard_asset_path()))).pack(side="left")

        def analyse() -> None:
            profile_frames = [candidate.frame_bgr for candidate in self.candidates] + list(self.reference_frames)
            profile = estimate_camera_profile(profile_frames)
            if profile is None:
                result_var.set(self._text("Need at least three sharp, distinct checkerboard views.", "Jsou potřeba alespoň tři ostré a odlišné pohledy na šachovnici."))
                return
            if self.calibration is not None:
                self.calibration = replace(self.calibration, camera_profile=profile)
                self.on_calibration_saved(self.calibration)
            result_var.set(self._text("Camera profile saved for this calibration.", "Profil kamery byl uložen pro tuto kalibraci."))

        ttk.Button(buttons, text=self._text("Analyse candidate frames", "Analyzovat vybrané snímky"), command=analyse).pack(side="left", padx=6)
        ttk.Button(buttons, text=self._text("Close", "Zavřít"), command=dialog.destroy).pack(side="right")

    def _render_projection(self) -> None:
        self.projection_canvas.delete("all")
        if self._active_view == "overhead":
            result = self._reconstruction_result
            if result is None:
                message = self._text("The estimated overhead shoe will appear when the local fit is reliable.", "Odhadovaná bota shora se zobrazí, až bude místní výpočet spolehlivý.")
                self.projection_canvas.create_text(
                    max(20, self.projection_canvas.winfo_width() / 2),
                    max(20, self.projection_canvas.winfo_height() / 2),
                    text=message, fill=self.palette["muted"],
                    width=max(200, self.projection_canvas.winfo_width() - 40),
                )
                return
            frame = result.overhead_image
            height, width = frame.shape[:2]
            canvas_width = max(300, self.projection_canvas.winfo_width())
            canvas_height = max(240, self.projection_canvas.winfo_height())
            scale = min(canvas_width / width, canvas_height / height)
            shown = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            self._projection_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)))
            self.projection_canvas.create_image(canvas_width / 2, canvas_height / 2, image=self._projection_photo, anchor="center")
            return
        candidate = self._current()
        if candidate is None or self.calibration is None or len(self._foot_points) < 3:
            message = self._text("Calibrate the pad and estimate or mark the foot.", "Kalibrujte prkno a odhadněte nebo označte botu.")
            self.projection_canvas.create_text(max(20, self.projection_canvas.winfo_width() / 2), max(20, self.projection_canvas.winfo_height() / 2), text=message, fill=self.palette["muted"], width=max(200, self.projection_canvas.winfo_width() - 40))
            return
        frame = candidate.frame_bgr
        frame_size = (frame.shape[1], frame.shape[0])
        length = self.calibration.pad_length_cm or STANDARD_BOARD_LENGTH_CM
        width = self.calibration.pad_width_cm or STANDARD_BOARD_WIDTH_CM
        ratio = max(1.5, min(7.0, length / width))
        pad_width, pad_height = 900, max(190, min(360, int(900 / ratio)))
        try:
            pad_homography = compute_physical_pad_homography(
                self.calibration.board_corners, self.calibration.foul_line, frame_size, (pad_width, pad_height)
            )
        except (ValueError, cv2.error) as exc:
            self.status_var.set(self._text(f"Calibration cannot be used: {exc}", f"Kalibraci nelze použít: {exc}"))
            return
        frame = undistort_frame_for_projection(frame, self.calibration)
        pad_image = cv2.warpPerspective(frame, pad_homography, (pad_width, pad_height))
        canvas_width = max(300, self.projection_canvas.winfo_width())
        canvas_height = max(240, self.projection_canvas.winfo_height())
        left, top = 35, 55
        right = canvas_width - 35
        bottom = min(canvas_height - 45, top + max(150, right - left) / ratio)
        quad = np.asarray([[left, top], [right, top + 18], [right, bottom], [left, bottom - 18]], dtype=np.float32)
        transform = cv2.getPerspectiveTransform(np.asarray([[0, 0], [pad_width - 1, 0], [pad_width - 1, pad_height - 1], [0, pad_height - 1]], dtype=np.float32), quad)
        base = np.full((canvas_height, canvas_width, 3), _hex_bgr(self.palette.get("video", "#03060a"), (3, 6, 10)), dtype=np.uint8)
        edge = np.asarray([[left, bottom - 18], [right, bottom], [right, bottom + 12], [left, bottom - 6]], dtype=np.int32)
        cv2.fillPoly(base, [edge], _hex_bgr(self.palette.get("border", "#2a374a"), (74, 55, 42)))
        projected = cv2.warpPerspective(pad_image, transform, (canvas_width, canvas_height))
        mask = cv2.warpPerspective(np.full((pad_height, pad_width), 255, dtype=np.uint8), transform, (canvas_width, canvas_height))
        base[mask > 0] = projected[mask > 0]
        measurement_points: Sequence[Sequence[float]] = self._foot_points
        fit_variation = 0.0
        measurement_confidence = self._foot_confidence or .65
        if self._reconstruction_result is not None:
            measurement_points = unproject_points_from_pad(
                self._reconstruction_result.sole_footprint,
                self.calibration.board_corners,
                frame_size,
            )
            fit_variation = self._reconstruction_result.fit_variation_cm
            measurement_confidence = min(measurement_confidence, self._reconstruction_result.fit_confidence)
        measurement = measure_projected_foot(
            measurement_points, self.calibration, frame_size,
            confidence=measurement_confidence,
            fit_variation_cm=fit_variation,
        )
        foul_normalized = project_points_to_pad(
            np.asarray(self.calibration.foul_line, dtype=np.float32) * np.asarray(frame_size, dtype=np.float32),
            self.calibration.board_corners,
            frame_size,
        )
        physical_axes_horizontal = abs(float(foul_normalized[1, 0] - foul_normalized[0, 0])) >= abs(float(foul_normalized[1, 1] - foul_normalized[0, 1]))

        def to_physical_axes(points: Sequence[Sequence[float]]) -> np.ndarray:
            values = np.asarray(points, dtype=np.float32)
            return values if physical_axes_horizontal else values[:, [1, 0]]

        def pad_to_canvas(points: Sequence[Sequence[float]]) -> np.ndarray:
            physical = to_physical_axes(points)
            points_px = np.asarray([[float(x) * (pad_width - 1), float(y) * (pad_height - 1)] for x, y in physical], dtype=np.float32).reshape((-1, 1, 2))
            return cv2.perspectiveTransform(points_px, transform).reshape((-1, 2)).astype(np.int32)
        footprint = self._reconstruction_result.sole_footprint if self._reconstruction_result is not None else estimated_footprint(measurement.polygon, self.calibration)
        foot_canvas = pad_to_canvas(footprint)
        foul_canvas = pad_to_canvas(foul_normalized)
        overlay = base.copy()
        cv2.fillPoly(overlay, [foot_canvas], (80, 190, 235))
        cv2.addWeighted(overlay, .38, base, .62, 0, base)
        cv2.polylines(base, [foot_canvas], True, (80, 220, 170), 3, cv2.LINE_AA)
        if len(foul_canvas) == 2:
            cv2.line(base, tuple(foul_canvas[0]), tuple(foul_canvas[1]), (100, 100, 255), 4, cv2.LINE_AA)
        cv2.polylines(base, [quad.astype(np.int32)], True, (220, 220, 220), 2, cv2.LINE_AA)
        label = "SOLE / CONTACT MEASUREMENT"
        label_color = (80, 220, 170)
        cv2.putText(base, "BOARD PROJECTION  |  DECISION SUPPORT", (18, 25), cv2.FONT_HERSHEY_SIMPLEX, .56, (220, 225, 235), 1, cv2.LINE_AA)
        cv2.putText(base, label, (left + 10, max(35, top - 12)), cv2.FONT_HERSHEY_SIMPLEX, .52, label_color, 2, cv2.LINE_AA)
        detail = f"Frame {candidate.frame_index + 1}  |  {candidate.score:.0%} shortlist"
        detail += f"  |  {measurement_display_text_ascii(measurement)}"
        cv2.putText(base, detail, (18, canvas_height - 15), cv2.FONT_HERSHEY_SIMPLEX, .48, (180, 190, 205), 1, cv2.LINE_AA)
        self._projection_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(base, cv2.COLOR_BGR2RGB)))
        self.projection_canvas.create_image(0, 0, image=self._projection_photo, anchor="nw")

    def _update_buttons(self) -> None:
        if not hasattr(self, "confirm_button"):
            return
        self.estimate_button.state(["!disabled"] if not self._calibrating and self.calibration is not None and self._current() else ["disabled"])
        self.edit_button.state(["!disabled"] if not self._calibrating and len(self._foot_points) >= 3 else ["disabled"])
        if self._calibrating:
            self.calibrate_button.configure(text=self._text("Start over", "Začít znovu"), command=self._start_calibration)
        else:
            self.calibrate_button.configure(text=self._text("Set up board", "Nastavit prkno"), command=self._start_calibration)
        self.confirm_button.state(["!disabled"] if not self._calibrating and self.calibration is not None and len(self._foot_points) >= 3 else ["disabled"])
        self.flip_side_button.state(["!disabled"] if not self._calibrating and self.calibration is not None else ["disabled"])

    def _confirm(self) -> None:
        if self.calibration is None or len(self._foot_points) < 3:
            return
        self.on_calibration_saved(self.calibration)
        self.on_confirm(self.attempt_id)
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._cancel_reconstruction()
        self._reconstruction_generation += 1
        try:
            self.window.destroy()
        finally:
            self.on_close()


class ProjectionProgressDialog:
    """Small modal determinate dialog driven only from the Tk thread."""

    def __init__(self, parent: tk.Misc, palette: dict[str, str], title: str, label: str, cancel: Callable[[], None], cancel_text: str = "Cancel", fullscreen: bool = False, preview_frame: np.ndarray | None = None) -> None:
        self.window = tk.Toplevel(parent)
        if not fullscreen:
            center_popup(self.window)
        self.window.title(title)
        self.window.transient(parent)
        self.window.resizable(False, False)
        self.window.configure(bg=palette["bg"])
        self.window.protocol("WM_DELETE_WINDOW", cancel)
        self._preview_canvas: tk.Canvas | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_frame = None if preview_frame is None else np.ascontiguousarray(preview_frame.copy())
        if fullscreen and self._preview_frame is not None:
            self._preview_canvas = tk.Canvas(self.window, bg="#0b1018", highlightthickness=0)
            self._preview_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
            bind_resize_only(self._preview_canvas, lambda _event: self._render_preview())
        frame = ttk.Frame(self.window, style="Panel.TFrame", padding=28 if fullscreen else 18)
        if fullscreen:
            frame.place(relx=0.5, rely=0.86, anchor="center", relwidth=0.72)
        else:
            frame.pack(fill="both", expand=True)
        self.label_var = tk.StringVar(value=label)
        self.detail_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.label_var, style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100, value=0, length=330, style="Modal.Horizontal.TProgressbar")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(frame, text=cancel_text, command=cancel).grid(row=1, column=1, padx=(10, 0))
        ttk.Label(frame, textvariable=self.detail_var, style="Muted.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        if fullscreen:
            # Open the review surface immediately. The determinate bar remains
            # the only progress indicator while frame loading is bounded.
            self.window.attributes("-fullscreen", True)
        self.window.grab_set()
        self.window.update_idletasks()
        self._render_preview()
        self.window.focus_force()

    def _render_preview(self) -> None:
        if self._preview_canvas is None or self._preview_frame is None:
            return
        frame = np.asarray(self._preview_frame)
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        elif frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        height, width = frame.shape[:2]
        canvas_width = max(1, self._preview_canvas.winfo_width())
        canvas_height = max(1, self._preview_canvas.winfo_height())
        panel_width = max(1, canvas_width // 2 - 20)
        scale = min(panel_width / max(1, width), (canvas_height - 54) / max(1, height))
        shown = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        self._preview_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)))
        self._preview_canvas.delete("all")
        left_x = canvas_width * .25
        right_x = canvas_width * .75
        self._preview_canvas.create_text(left_x, 18, text="Original camera frame", fill="#d8e2ed", font=("Segoe UI", 14, "bold"))
        self._preview_canvas.create_text(right_x, 18, text="Computed top-down view", fill="#d8e2ed", font=("Segoe UI", 14, "bold"))
        self._preview_canvas.create_line(canvas_width / 2, 0, canvas_width / 2, canvas_height, fill="#31404e", width=2)
        self._preview_canvas.create_image(left_x - shown.shape[1] / 2, 42 + (canvas_height - 54 - shown.shape[0]) / 2, image=self._preview_photo, anchor="nw")
        self._preview_canvas.create_text(right_x, canvas_height / 2, text="Waiting for computed\ntop-down projection…", fill="#b8c5d2", justify="center", font=("Segoe UI", 16))

    def update(self, value: float, label: str | None = None, detail: str | None = None) -> None:
        if label is not None:
            self.label_var.set(label)
        if detail is not None:
            self.detail_var.set(detail)
        self.progress.configure(value=max(float(self.progress["value"]), min(99.0, float(value))))

    def close(self) -> None:
        try:
            if self.window.winfo_exists():
                self.window.grab_release()
                self.window.destroy()
        except tk.TclError:
            pass

    def complete(self, label: str) -> None:
        self.label_var.set(label)
        self.progress.configure(value=100)
        self.window.update_idletasks()


class TopViewProjectionWindow:
    """Unified automatic analysis and top-down projection workspace."""

    def __init__(
        self,
        master: tk.Misc,
        palette: dict[str, str],
        language: str,
        attempt_id: int,
        packets: Sequence[FramePacket],
        target_timestamp_ns: int,
        roi: Sequence[float],
        calibration: ProjectionCalibration | None,
        calibration_warning: str,
        camera_signature: str,
        on_calibration_saved: Callable[[ProjectionCalibration], None],
        on_confirm: Callable[[int], None],
        on_close: Callable[[], None],
        candidates: Sequence[ProjectionCandidate] | None = None,
        reference_frames: Sequence[np.ndarray] | None = None,
        candidate_estimates: dict[int, FootEstimate] | None = None,
        foul_area: Sequence[Sequence[float]] = (),
        on_foul_area_saved: Callable[[tuple[tuple[float, float], ...]], None] | None = None,
        start_fullscreen: bool = False,
        auto_start: bool = True,
        automatic_advisory_status: str = "",
        automatic_advisory_label: str = "",
        automatic_advisory_confidence: float | None = None,
    ) -> None:
        self.master, self.palette, self.language = master, palette, language
        self.attempt_id, self.packets = attempt_id, list(packets)
        self.target_timestamp_ns, self.roi = int(target_timestamp_ns), tuple(roi)
        self.camera_signature = camera_signature
        self.on_calibration_saved, self.on_confirm, self.on_close = on_calibration_saved, on_confirm, on_close
        self.on_foul_area_saved = on_foul_area_saved
        self._saved_foul_area = tuple(tuple(map(float, point)) for point in foul_area)
        self.calibration, self.calibration_warning = calibration, calibration_warning
        self.candidates = list(candidates or [])
        self.reference_frames = [frame for frame in (reference_frames or ()) if frame is not None]
        self._candidate_estimates = dict(candidate_estimates or {})
        self.automatic_advisory_status = str(automatic_advisory_status).strip().lower()
        self.automatic_advisory_label = str(automatic_advisory_label).strip()
        self.automatic_advisory_confidence = (
            None
            if automatic_advisory_confidence is None
            else max(0.0, min(1.0, float(automatic_advisory_confidence)))
        )
        self.current_candidate = 0
        self._state = "selecting_frame"
        self._closed = False
        self._generation = 0
        self._cancel: Event | None = None
        self._queue: Queue[tuple[int, str, object]] = Queue()
        self._analysis_dialog: ProjectionProgressDialog | None = None
        self._analysis: ProjectionAnalysisResult | None = None
        self._analysis_failure: dict[str, object] | None = None
        self._board_result: np.ndarray | None = None
        self._overhead_result: ReconstructionResult | None = None
        self._active_compute: str | None = None
        self._edit_layer: str | None = None
        self._drag_index: int | None = None
        self._board_points: list[tuple[float, float]] = []
        self._foul_points: list[tuple[float, float]] = []
        self._foul_area_points: list[tuple[float, float]] = []
        self._foot_points: list[tuple[float, float]] = []
        self._foot_confidence = 0.0
        self._source_bounds = (0.0, 0.0, 1.0, 1.0)
        self._source_frame_size = (0, 0)
        self._selection_bounds = (0.0, 0.0, 1.0, 1.0)
        self._shoe_search_roi: tuple[float, float, float, float] = ()
        self._shoe_candidate_points: list[tuple[tuple[float, float], ...]] = []
        self._selection_photo = self._source_photo = self._board_photo = self._overhead_photo = self._zoom_photo = None
        self._fullscreen_window: tk.Toplevel | None = None
        self._fullscreen_canvas: tk.Canvas | None = None
        self._fullscreen_image: np.ndarray | None = None
        self._fullscreen_photo: ImageTk.PhotoImage | None = None
        self._fullscreen_scale = 1.0
        self._fullscreen_offset = (0.0, 0.0)
        self._fullscreen_fit_scale = 1.0
        self._fullscreen_drag_start: tuple[float, float] | None = None
        self._split_review_window: tk.Toplevel | None = None
        self._split_review_photos: list[ImageTk.PhotoImage] = []
        self._split_review_render: Callable[[], None] | None = None
        self._split_review_progress: ttk.Progressbar | None = None
        self._split_review_stage_var: tk.StringVar | None = None
        self._split_review_badge: tk.Label | None = None
        self._split_review_detail: tk.Label | None = None
        self._split_review_reveal_image: np.ndarray | None = None
        self._split_review_animation_job: str | None = None
        self._brush_trace: list[tuple[float, float]] = []
        self._compute_started_at = 0.0
        self._last_compute_duration_ms = 0.0
        self._magnifier_factor = 3.0
        self._magnifier_target: tuple[float, float] | None = None
        self._magnifier_focus: tuple[float, float] | None = None
        self._magnifier_canvas_point = (0.0, 0.0)
        self._magnifier_job: str | None = None
        self._result_bounds = (0.0, 0.0, 1.0, 1.0)
        self._result_target: tuple[float, float] | None = None
        self._result_focus: tuple[float, float] | None = None
        self._result_canvas_point = (0.0, 0.0)
        self._result_magnifier_job: str | None = None

        self.window = tk.Toplevel(master)
        if not start_fullscreen:
            center_popup(self.window)
        self.window.title(self._text("Top-down projection", "Projekce shora"))
        self.window.geometry("1220x790")
        self.window.minsize(940, 650)
        self.window.configure(bg=palette["bg"])
        if start_fullscreen:
            self.window.attributes("-fullscreen", True)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)

        header = ttk.Frame(self.window, style="Panel.TFrame", padding=(14, 10))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=self._text("TOP-DOWN PROJECTION", "PROJEKCE SHORA"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text=self._text("Decision support only - the original frame remains authoritative.", "Pouze podpůrné zobrazení - původní snímek zůstává rozhodující."), style="Muted.TLabel").pack(anchor="w", pady=(3, 0))

        self.selection_page = ttk.Frame(self.window, style="Panel.TFrame", padding=10)
        self.selection_page.grid(row=1, column=0, sticky="nsew")
        self.selection_page.rowconfigure(1, weight=1); self.selection_page.columnconfigure(1, weight=1)
        ttk.Label(self.selection_page, text=self._text("Choose the frame that best shows the shoe at take-off.", "Vyberte snímek, který nejlépe zachycuje botu při odrazu."), style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        thumb_host = ttk.Frame(self.selection_page, style="Toolbar.TFrame", padding=5)
        thumb_host.grid(row=1, column=0, sticky="ns", padx=(0, 8))
        self.thumbnail_canvas = tk.Canvas(thumb_host, width=178, bg=palette["surface2"], highlightthickness=0)
        self.thumbnail_canvas.pack(side="left", fill="y")
        thumb_scroll = ttk.Scrollbar(thumb_host, orient="vertical", command=self.thumbnail_canvas.yview)
        thumb_scroll.pack(side="right", fill="y")
        self.thumbnail_canvas.configure(yscrollcommand=thumb_scroll.set)
        self.thumbnail_inner = ttk.Frame(self.thumbnail_canvas, style="Toolbar.TFrame")
        self.thumbnail_canvas.create_window((0, 0), window=self.thumbnail_inner, anchor="nw")
        self.thumbnail_inner.bind("<Configure>", lambda _e: self.thumbnail_canvas.configure(scrollregion=self.thumbnail_canvas.bbox("all")))
        self._thumbnail_photos: list[ImageTk.PhotoImage] = []
        self._thumbnail_labels: list[tk.Label] = []
        for index, candidate in enumerate(self.candidates):
            label = tk.Label(self.thumbnail_inner, bg=palette["surface2"], bd=2, relief="flat", cursor="hand2")
            label.pack(padx=4, pady=4)
            label.bind("<Button-1>", lambda _event, index=index: self._select_candidate(index))
            photo = self._photo(candidate.frame_bgr, (160, 100))
            label.configure(image=photo)
            self._thumbnail_photos.append(photo); self._thumbnail_labels.append(label)
        self.selection_canvas = tk.Canvas(self.selection_page, bg=palette["video"], highlightthickness=1, highlightbackground=palette["border"])
        self.selection_canvas.grid(row=1, column=1, sticky="nsew")
        bind_resize_only(self.selection_canvas, lambda _e: self._render_selection())
        self.selection_canvas.bind("<Motion>", self._selection_hover)
        self.selection_canvas.bind("<Leave>", lambda _e: self.selection_canvas.delete("zoom"))
        selection_actions = ttk.Frame(self.selection_page, style="Panel.TFrame")
        selection_actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(9, 0))
        self.manual_setup_button = ttk.Button(
            selection_actions,
            text=self._text("Set up manually", "Nastavit ručně"),
            style="Toolbar.TButton",
            command=self._open_manual_setup,
        )
        self.manual_setup_button.pack_forget()
        self.confirm_frame_button = ttk.Button(selection_actions, text=self._text("Confirm frame", "Potvrdit snímek"), style="Primary.TButton", command=self._confirm_frame)
        self.confirm_frame_button.pack(side="left", padx=(0, 6))
        ttk.Button(selection_actions, text=self._text("Cancel", "Zrušit"), style="Toolbar.TButton", command=self.close).pack(side="left")

        self.workspace_page = ttk.Frame(self.window, style="Panel.TFrame", padding=10)
        self.workspace_page.rowconfigure(2, weight=3); self.workspace_page.columnconfigure(0, weight=1)
        toolbar = ttk.Frame(self.workspace_page, style="Toolbar.TFrame", padding=(7, 5))
        toolbar.grid(row=0, column=0, sticky="ew")
        style = ttk.Style(self.window)
        style.configure("Projection.TCheckbutton", padding=(5, 3), font=("Segoe UI", 10))
        style.configure("ProjectionCategory.TLabel", font=("Segoe UI Semibold", 8), foreground=palette["muted"], background=palette["surface2"])
        self.mouse_zoom_var = tk.BooleanVar(value=False)
        self.brush_snap_var = tk.BooleanVar(value=False)
        # Keep the source camera view clean by default; computed geometry can
        # still be enabled explicitly with Show outlines when needed.
        self.show_outlines_var = tk.BooleanVar(value=False)
        self.debug_overlay_var = tk.BooleanVar(value=False)
        self._toolbar_buttons: list[ttk.Button] = []
        self._edit_toolbar_buttons: list[ttk.Button] = []
        self._toolbar_category_labels: list[ttk.Label] = []
        for text_pair, command in (
            (("Back to frames", "Zpět na snímky"), self._go_back),
            (("Re-analyse", "Znovu analyzovat"), self._confirm_frame),
            (("Edit board", "Upravit prkno"), lambda: self._set_edit_layer("board")),
            (("Edit foul line", "Upravit odrazovou čáru"), lambda: self._set_edit_layer("foul")),
            (("Edit shoe", "Upravit botu"), lambda: self._set_edit_layer("shoe")),
            (("Flip legal side", "Obrátit platnou stranu"), self._flip_legal_side),
            (("Advanced camera...", "Pokročilá kamera..."), self._open_camera_profile_wizard),
        ):
            if text_pair[0].startswith("Advanced camera"):
                continue
            if not self._toolbar_buttons:
                label = ttk.Label(toolbar, text=self._text("NAVIGATE", "NAVIGACE"), style="ProjectionCategory.TLabel"); label.pack(side="left", padx=(0, 4)); self._toolbar_category_labels.append(label)
            elif len(self._toolbar_buttons) == 2:
                label = ttk.Label(toolbar, text=self._text("EDIT", "ÚPRAVY"), style="ProjectionCategory.TLabel"); label.pack(side="left", padx=(4, 4)); self._toolbar_category_labels.append(label)
            elif len(self._toolbar_buttons) == 5:
                label = ttk.Label(toolbar, text=self._text("CALIBRATION", "KALIBRACE"), style="ProjectionCategory.TLabel"); label.pack(side="left", padx=(4, 4)); self._toolbar_category_labels.append(label)
            button = ttk.Button(toolbar, text=self._text(*text_pair), style="Toolbar.TButton", command=command)
            button.pack(side="left", padx=(0, 5))
            self._toolbar_buttons.append(button)
            if len(self._toolbar_buttons) in {3, 4, 5}:
                self._edit_toolbar_buttons.append(button)
        self.mouse_zoom_checkbutton = ttk.Checkbutton(
            toolbar,
            text=self._text("Mouse zoom", "Lupa myší"),
            variable=self.mouse_zoom_var,
            command=self._toggle_mouse_zoom,
        )
        self.mouse_zoom_checkbutton.configure(style="Projection.TCheckbutton")
        self.view_category_label = ttk.Label(toolbar, text=self._text("VIEW", "ZOBRAZENÍ"), style="ProjectionCategory.TLabel")
        self.view_category_label.pack(side="left", padx=(4, 4))
        self._toolbar_category_labels.append(self.view_category_label)
        self.mouse_zoom_checkbutton.pack(side="left", padx=(0, 8))
        self.show_outlines_checkbutton = ttk.Checkbutton(
            toolbar,
            text=self._text("Show outlines", "Zobrazit obrysy"),
            variable=self.show_outlines_var,
            command=self._toggle_outlines,
            style="Projection.TCheckbutton",
        )
        self.show_outlines_checkbutton.pack(side="left", padx=(0, 8))
        self.debug_overlay_checkbutton = ttk.Checkbutton(
            toolbar,
            text=self._text("Detection debug", "Diagnostika detekce"),
            variable=self.debug_overlay_var,
            command=self._toggle_debug_overlay,
            style="Projection.TCheckbutton",
        )
        self.debug_overlay_checkbutton.pack(side="left", padx=(0, 8))
        self.brush_snap_checkbutton = ttk.Checkbutton(
            toolbar,
            text=self._text("Brush edge snap", "Štětec s přichycením"),
            variable=self.brush_snap_var,
            command=self._toggle_brush_snap,
            style="Projection.TCheckbutton",
        )
        self.brush_snap_checkbutton.pack_forget()
        self.edit_done_button = ttk.Button(toolbar, text=self._text("Done", "Hotovo"), style="Primary.TButton", command=lambda: self._set_edit_layer(None))
        self.edit_done_button.pack_forget()
        self.close_button = ttk.Button(toolbar, text=self._text("Close", "Zavřít"), style="Toolbar.TButton", command=self.close)
        self.close_button.pack(side="right")
        self.split_review_button = ttk.Button(
            toolbar,
            text=self._text("Show split review", "Zobrazit porovnání"),
            style="Toolbar.TButton",
            command=self._show_split_review_again,
        )
        self.split_review_button.pack(side="right", padx=(0, 5))
        self.split_review_button.state(["disabled"])
        self.source_canvas = tk.Canvas(self.workspace_page, height=220, bg=palette["video"], highlightthickness=1, highlightbackground=palette["border"])
        self.source_canvas.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        bind_resize_only(self.source_canvas, lambda _e: self._render_source())
        self.source_canvas.bind("<ButtonPress-1>", self._source_press)
        self.source_canvas.bind("<B1-Motion>", self._source_drag)
        self.source_canvas.bind("<ButtonRelease-1>", self._source_release)
        self.source_canvas.bind("<ButtonPress-3>", self._source_remove_point)
        self.source_canvas.bind("<Motion>", self._source_hover, add="+")
        self.source_canvas.bind("<Leave>", self._hide_source_magnifier)
        self.source_canvas.bind("<MouseWheel>", self._source_magnifier_wheel)
        self.source_canvas.bind("<Button-4>", self._source_magnifier_wheel)
        self.source_canvas.bind("<Button-5>", self._source_magnifier_wheel)
        self.source_canvas.bind("<Double-Button-1>", self._reset_magnifier)

        self.projections_frame = ttk.Frame(self.workspace_page, style="Panel.TFrame")
        self.projections_frame.grid(row=2, column=0, sticky="nsew")
        self.projections_frame.rowconfigure(0, weight=1); self.projections_frame.columnconfigure(0, weight=1)
        # One unified projection is the operator-facing output.  Keep the
        # board canvas object as a compatibility shim for older GUI callers,
        # but do not place it or expose a second Compute action.
        self.board_canvas, self.board_compute_button = self._projection_panel(self.projections_frame, 0, self._text("Board projection", "Projekce prkna"), "board")
        self.board_canvas.master.grid_remove()
        self.board_compute_button.pack_forget()
        self.overhead_canvas, self.overhead_compute_button = self._projection_panel(self.projections_frame, 0, self._text("Top-down board view", "Pohled na prkno shora"), "overhead")
        self.progress_frame = ttk.Frame(self.workspace_page, style="Panel.TFrame")
        self.progress_frame.grid(row=3, column=0, sticky="ew", pady=(7, 0)); self.progress_frame.columnconfigure(0, weight=1)
        self.progress_label_var = tk.StringVar(value="")
        ttk.Label(self.progress_frame, textvariable=self.progress_label_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.reconstruction_progress = ttk.Progressbar(self.progress_frame, mode="determinate", maximum=100, value=0, style="Modal.Horizontal.TProgressbar")
        self.reconstruction_progress.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.reconstruction_stage_var = self.progress_label_var
        self.status_var = tk.StringVar(value="")
        self.status_line = ttk.Label(self.workspace_page, textvariable=self.status_var, style="Status.TLabel")
        self.status_line.grid(row=4, column=0, sticky="w", pady=(5, 0))
        self.progress_frame.grid_remove()

        self.window.bind("<Return>", lambda _e: self._confirm_frame() if self._state == "selecting_frame" else None)
        if self.candidates:
            # The caller supplies exactly the frame currently shown in replay.
            # Keep the old selection widgets constructed for compatibility with
            # older callers, but never expose that page in the active workflow.
            self.current_candidate = min(range(len(self.candidates)), key=lambda index: abs(self.candidates[index].timestamp_ns - self.target_timestamp_ns))
            self._select_candidate(self.current_candidate)
            self.selection_page.grid_remove()
            if auto_start:
                self.window.after_idle(self._confirm_frame)
            else:
                self._state = "loading_frames"
                self.selection_page.grid_remove()
                self.workspace_page.grid(row=1, column=0, sticky="nsew")
                self.window.after_idle(self._render_source)
        else:
            self.confirm_frame_button.state(["disabled"])
        self.window.update_idletasks()
        self.window.after(40, self._poll_queue)

    def _text(self, english: str, czech: str) -> str:
        return czech if self.language == "cs" else english

    def _automatic_verdict_display(self) -> tuple[str, str, float] | None:
        """Return the persisted Auto/Takeoff Assist verdict used by the main view."""
        status = getattr(self, "automatic_advisory_status", "")
        if status not in {"valid", "foul", "review"}:
            return None
        fallback_labels = {
            "valid": self._text("LIKELY VALID", "PRAVDĚPODOBNĚ PLATNÝ"),
            "foul": self._text("LIKELY FOUL", "PRAVDĚPODOBNĚ PŘEŠLAP"),
            "review": self._text("REVIEW REQUIRED", "NUTNÁ KONTROLA"),
        }
        colours = {
            "valid": self.palette["live"],
            "foul": self.palette["danger"],
            "review": self.palette["warning"],
        }
        label = getattr(self, "automatic_advisory_label", "") or fallback_labels[status]
        confidence = getattr(self, "automatic_advisory_confidence", None)
        return label, colours[status], 0.0 if confidence is None else float(confidence)

    def _verdict_display(self, projection_status: str, projection_confidence: float) -> tuple[str, str, float]:
        automatic = self._automatic_verdict_display()
        if automatic is not None:
            return automatic
        label = projection_verdict_text(projection_status)
        colour = (
            self.palette["danger"] if projection_status == "over"
            else self.palette["live"] if projection_status == "clear"
            else self.palette["warning"]
        )
        return label, colour, max(0.0, min(1.0, float(projection_confidence)))

    @staticmethod
    def _display_frame(frame: np.ndarray) -> np.ndarray:
        """Return a contiguous uint8 BGR image that Tk/Pillow can display safely."""
        shown = np.asarray(frame)
        if shown.ndim == 2:
            shown = cv2.cvtColor(shown, cv2.COLOR_GRAY2BGR)
        elif shown.ndim == 3 and shown.shape[2] == 4:
            shown = cv2.cvtColor(shown, cv2.COLOR_BGRA2BGR)
        elif shown.ndim != 3 or shown.shape[2] != 3:
            raise ValueError(f"Unsupported projection image shape: {shown.shape}")
        if shown.dtype != np.uint8:
            shown = np.nan_to_num(shown, nan=0.0, posinf=255.0, neginf=0.0)
            shown = np.clip(shown, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(shown)

    @staticmethod
    def _photo(frame: np.ndarray, size: tuple[int, int]) -> ImageTk.PhotoImage:
        frame = TopViewProjectionWindow._display_frame(frame)
        height, width = frame.shape[:2]
        scale = min(size[0] / max(1, width), size[1] / max(1, height))
        shown = cv2.resize(frame, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)))

    def _current(self) -> ProjectionCandidate | None:
        return self.candidates[self.current_candidate] if self.candidates else None

    def open_pending_review(self) -> None:
        """Show the authoritative original frame before background loading."""
        if self._closed:
            return
        self._open_split_review()
        review = self._split_review_window
        if review is not None:
            review.lift()
            review.focus_force()

    def update_loading_progress(self, value: float, detail: str) -> None:
        """Update only the already-visible split review; never open another UI."""
        self._update_split_review_progress(min(12.0, max(0.0, float(value) * 0.12)), detail)

    def begin_automatic_analysis(
        self,
        candidates: Sequence[ProjectionCandidate],
        reference_frames: Sequence[np.ndarray],
        candidate_estimates: dict[int, FootEstimate],
        target_timestamp_ns: int,
        roi: Sequence[float],
        calibration: ProjectionCalibration | None,
        calibration_warning: str,
    ) -> None:
        """Attach loaded inputs and continue inside the existing split review."""
        if self._closed or not candidates:
            return
        self.candidates = list(candidates)
        self.reference_frames = [frame for frame in reference_frames if frame is not None]
        self._candidate_estimates = dict(candidate_estimates)
        self.target_timestamp_ns = int(target_timestamp_ns)
        self.roi = tuple(roi)
        self.calibration = calibration
        self.calibration_warning = calibration_warning
        self.current_candidate = min(range(len(self.candidates)), key=lambda index: abs(self.candidates[index].timestamp_ns - self.target_timestamp_ns))
        self._state = "selecting_frame"
        self._render_source()
        if self._split_review_render is not None:
            self._split_review_render()
        self._confirm_frame()
        if self._split_review_window is not None:
            self.window.after_idle(lambda: (
                self._split_review_window.lift(),
                self._split_review_window.focus_force(),
            ) if self._split_review_window is not None else None)

    def _projection_panel(self, parent: ttk.Frame, column: int, title: str, target: str) -> tuple[tk.Canvas, ttk.Button]:
        panel = ttk.Frame(parent, style="Panel.TFrame", padding=5)
        panel.grid(row=0, column=column, sticky="nsew", padx=(0, 4) if column == 0 else (4, 0))
        panel.rowconfigure(1, weight=1); panel.columnconfigure(0, weight=1)
        heading = ttk.Frame(panel, style="Panel.TFrame")
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        ttk.Label(heading, text=title, style="Title.TLabel", font=("Segoe UI Semibold", 12)).pack(side="left")
        if target == "overhead":
            automatic = self._automatic_verdict_display()
            initial_badge = automatic[0] if automatic is not None else self._text("WAITING", "ČEKÁ")
            initial_confidence = (
                self._text(f"Confidence {automatic[2]:.0%}", f"Spolehlivost {automatic[2]:.0%}")
                if automatic is not None else ""
            )
            self.result_badge_var = tk.StringVar(value=initial_badge)
            self.result_confidence_var = tk.StringVar(value=initial_confidence)
            self.result_badge = tk.Label(
                heading,
                textvariable=self.result_badge_var,
                padx=10,
                pady=2,
                font=("Segoe UI Semibold", 10),
                bg=automatic[1] if automatic is not None else self.palette["surface2"],
                fg=(
                    "#ffffff" if automatic is not None and self.automatic_advisory_status in {"valid", "foul"}
                    else "#111722" if automatic is not None
                    else self.palette["muted"]
                ),
            )
            self.result_badge.pack(side="left", padx=(12, 7))
            ttk.Label(heading, textvariable=self.result_confidence_var, style="Muted.TLabel").pack(side="left")
            ttk.Label(
                heading,
                text=self._text("Calibrated board and foul line", "Kalibrované prkno a odrazová čára"),
                style="Muted.TLabel",
            ).pack(side="right")
        canvas = tk.Canvas(panel, bg=self.palette["video"], highlightthickness=1, highlightbackground=self.palette["border"])
        canvas.grid(row=1, column=0, sticky="nsew")
        compute_target = "board" if target == "overhead" else target
        button = ttk.Button(panel, text=self._text("Compute", "Vypočítat"), style="Primary.TButton", command=lambda target=compute_target: self._compute(target))
        bind_resize_only(canvas, lambda _e, target=target: self._render_result(target))
        canvas.bind("<Button-1>", lambda event, target=target: self._open_fullscreen(target, event))
        if target == "overhead":
            canvas.bind("<Motion>", self._result_hover, add="+")
            canvas.bind("<Leave>", self._hide_result_magnifier)
            canvas.bind("<MouseWheel>", self._result_magnifier_wheel)
            canvas.bind("<Button-4>", self._result_magnifier_wheel)
            canvas.bind("<Button-5>", self._result_magnifier_wheel)
            canvas.bind("<Double-Button-1>", self._reset_magnifier)
        return canvas, button

    def _select_candidate(self, index: int) -> None:
        if not self.candidates or self._state != "selecting_frame":
            return
        self.current_candidate = max(0, min(len(self.candidates) - 1, int(index)))
        for candidate_index, label in enumerate(self._thumbnail_labels):
            label.configure(relief="solid" if candidate_index == self.current_candidate else "flat", highlightbackground=self.palette["accent"] if candidate_index == self.current_candidate else self.palette["surface2"])
        self._render_selection()

    def _render_selection(self) -> None:
        candidate = self._current()
        self.selection_canvas.delete("all")
        if candidate is None:
            return
        frame = candidate.frame_bgr
        cw, ch = max(200, self.selection_canvas.winfo_width()), max(160, self.selection_canvas.winfo_height())
        scale = min((cw - 20) / frame.shape[1], (ch - 20) / frame.shape[0])
        rw, rh = max(1, int(frame.shape[1] * scale)), max(1, int(frame.shape[0] * scale))
        left, top = (cw - rw) / 2, (ch - rh) / 2
        self._selection_photo = self._photo(frame, (rw, rh))
        self.selection_canvas.create_image(left, top, image=self._selection_photo, anchor="nw", tags="frame")
        self.selection_canvas.create_text(12, 12, text=f"FRAME {candidate.frame_index + 1}", fill=self.palette["text"], anchor="nw")
        self._selection_bounds = (left, top, left + rw, top + rh)

    def _hover_zoom(self, canvas: tk.Canvas, bounds: tuple[float, float, float, float], frame: np.ndarray, event) -> str:
        left, top, right, bottom = bounds
        if not (left <= event.x <= right and top <= event.y <= bottom):
            canvas.delete("zoom"); return "break"
        fx = int((event.x - left) / max(1.0, right - left) * frame.shape[1]); fy = int((event.y - top) / max(1.0, bottom - top) * frame.shape[0])
        crop_w, crop_h = max(40, frame.shape[1] // 8), max(30, frame.shape[0] // 8)
        x0, y0 = max(0, fx - crop_w // 2), max(0, fy - crop_h // 2)
        crop = frame[y0:min(frame.shape[0], y0 + crop_h), x0:min(frame.shape[1], x0 + crop_w)]
        if crop.size == 0: return "break"
        zoom = cv2.resize(crop, (220, 140), interpolation=cv2.INTER_LINEAR)
        self._zoom_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(zoom, cv2.COLOR_BGR2RGB)))
        canvas.delete("zoom")
        x = min(max(112, event.x + 120), max(112, canvas.winfo_width() - 112)); y = min(max(72, event.y + 80), max(72, canvas.winfo_height() - 72))
        canvas.create_image(x, y, image=self._zoom_photo, anchor="center", tags="zoom")
        return "break"

    def _selection_hover(self, event) -> str:
        candidate = self._current()
        return self._hover_zoom(self.selection_canvas, self._selection_bounds, candidate.frame_bgr, event) if candidate else "break"

    def _source_hover(self, event) -> str:
        candidate = self._current()
        if event is None or not self.mouse_zoom_var.get() or candidate is None:
            self.source_canvas.delete("zoom")
            return "break"
        point = self._canvas_to_frame(event.x, event.y)
        if point is None:
            self.source_canvas.delete("zoom")
            return "break"
        self._magnifier_target = point
        self._magnifier_canvas_point = (float(event.x), float(event.y))
        if self._magnifier_focus is None:
            self._magnifier_focus = point
        if self._magnifier_job is None:
            self._magnifier_job = self.window.after(20, self._update_source_magnifier)
        return "break"

    def _update_source_magnifier(self) -> None:
        self._magnifier_job = None
        if self._closed or not self.mouse_zoom_var.get() or self._magnifier_target is None:
            return
        target = np.asarray(self._magnifier_target, np.float32)
        current = np.asarray(self._magnifier_focus or self._magnifier_target, np.float32)
        current += (target - current) * .48
        self._magnifier_focus = (float(current[0]), float(current[1]))
        self._draw_source_magnifier()
        if float(np.linalg.norm(target - current)) > .35:
            self._magnifier_job = self.window.after(20, self._update_source_magnifier)

    def _draw_source_magnifier(self) -> None:
        candidate = self._current()
        if candidate is None or self._magnifier_focus is None:
            return
        frame = candidate.frame_bgr
        left, top, right, bottom = self._source_bounds
        display_width, display_height = max(1.0, right-left), max(1.0, bottom-top)
        zoom_w, zoom_h = 320, 210
        crop_w = max(24, min(frame.shape[1], int(round(zoom_w / self._magnifier_factor * frame.shape[1] / display_width))))
        crop_h = max(18, min(frame.shape[0], int(round(zoom_h / self._magnifier_factor * frame.shape[0] / display_height))))
        fx, fy = self._magnifier_focus
        x0 = max(0, min(frame.shape[1]-crop_w, int(round(fx-crop_w/2))))
        y0 = max(0, min(frame.shape[0]-crop_h, int(round(fy-crop_h/2))))
        crop = frame[y0:y0+crop_h, x0:x0+crop_w].copy()
        if crop.size == 0: return
        zoom = cv2.resize(crop, (zoom_w, zoom_h), interpolation=cv2.INTER_CUBIC)
        scale_x, scale_y = zoom_w / max(1, crop.shape[1]), zoom_h / max(1, crop.shape[0])
        colors = {"board": (79, 189, 245), "foul": (117, 102, 255), "shoe": (165, 214, 112)}
        for layer, points, color in (("board", self._board_points, colors["board"]), ("foul", self._foul_area_points or self._foul_points, colors["foul"]), ("shoe", self._foot_points, colors["shoe"])):
            if not self.show_outlines_var.get() and layer != self._edit_layer:
                continue
            if len(points) < 2:
                continue
            local = np.asarray([((px - x0) * scale_x, (py - y0) * scale_y) for px, py in points], dtype=np.float32)
            visible = (local[:, 0] >= -8) & (local[:, 0] <= zoom_w + 8) & (local[:, 1] >= -8) & (local[:, 1] <= zoom_h + 8)
            if not np.any(visible):
                continue
            polyline = np.rint(local).astype(np.int32).reshape((-1, 1, 2))
            if layer in {"board", "foul"} and len(polyline) >= 4:
                cv2.polylines(zoom, [polyline], True, color, 3, cv2.LINE_AA)
            elif layer == "shoe" and len(polyline) >= 3:
                cv2.polylines(zoom, [polyline], True, color, 3, cv2.LINE_AA)
            else:
                cv2.polylines(zoom, [polyline], False, color, 3, cv2.LINE_AA)
            if layer == self._edit_layer:
                for px, py in polyline.reshape((-1, 2)):
                    cv2.circle(zoom, (int(px), int(py)), 4, (20, 25, 30), -1, cv2.LINE_AA)
                    cv2.circle(zoom, (int(px), int(py)), 3, color, -1, cv2.LINE_AA)
        cross_x = int(round((fx-x0)*scale_x)); cross_y = int(round((fy-y0)*scale_y))
        cv2.line(zoom, (cross_x-9, cross_y), (cross_x+9, cross_y), (235, 241, 247), 1, cv2.LINE_AA)
        cv2.line(zoom, (cross_x, cross_y-9), (cross_x, cross_y+9), (235, 241, 247), 1, cv2.LINE_AA)
        cv2.rectangle(zoom, (0, 0), (zoom_w-1, zoom_h-1), (205, 220, 235), 1)
        self._zoom_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(zoom, cv2.COLOR_BGR2RGB)))
        self.source_canvas.delete("zoom")
        event_x, event_y = self._magnifier_canvas_point
        self.source_canvas.create_rectangle(event_x - 18, event_y - 18, event_x + 18, event_y + 18, outline="#fff1a8", width=2, tags="zoom")
        px = min(max(zoom_w/2+5, event_x + zoom_w/2+18), max(zoom_w/2+5, self.source_canvas.winfo_width() - zoom_w/2-5))
        py = min(max(zoom_h/2+5, event_y + zoom_h/2+18), max(zoom_h/2+5, self.source_canvas.winfo_height() - zoom_h/2-5))
        self.source_canvas.create_image(px, py, image=self._zoom_photo, anchor="center", tags="zoom")

    def _source_magnifier_wheel(self, event) -> str:
        if not self.mouse_zoom_var.get(): return "break"
        direction = 1 if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0 else -1
        self._magnifier_factor = max(1.5, min(8.0, self._magnifier_factor * (1.16 if direction > 0 else 1/1.16)))
        self._source_hover(event)
        return "break"

    def _reset_magnifier(self, _event=None) -> str:
        self._magnifier_factor = 3.0
        self._magnifier_focus = self._magnifier_target
        if self.mouse_zoom_var.get(): self._draw_source_magnifier()
        return "break"

    def _toggle_mouse_zoom(self) -> None:
        enabled = bool(self.mouse_zoom_var.get())
        self._hide_source_magnifier()
        self._hide_result_magnifier()
        self.source_canvas.configure(cursor="crosshair" if self._edit_layer is not None else ("tcross" if enabled else "arrow"))
        self.status_var.set(
            self._text("Mouse zoom on.", "Přiblížení myší zapnuto.")
            if enabled
            else self._text("Mouse zoom off.", "Přiblížení myší vypnuto.")
        )

    def _hide_source_magnifier(self, _event=None) -> None:
        self._magnifier_target = None
        if self._magnifier_job is not None:
            try: self.window.after_cancel(self._magnifier_job)
            except tk.TclError: pass
            self._magnifier_job = None
        self.source_canvas.delete("zoom")

    def _toggle_brush_snap(self) -> None:
        self._brush_trace.clear()
        self.status_var.set(self._text(
            "Brush edge snap on. Paint once around the shoe boundary; release to snap the outline to nearby edges.",
            "Přichycení štětce je zapnuté. Jedním tahem obkreslete hranici boty; po uvolnění se obrys přichytí k blízkým hranám.",
        ) if self.brush_snap_var.get() else self._text(
            "Point editing restored.", "Obnovena úprava jednotlivých bodů.",
        ))

    def _toggle_outlines(self) -> None:
        visible = bool(self.show_outlines_var.get())
        self.source_canvas.delete("zoom")
        self._render_source()
        candidate = self._current()
        if self._board_result is not None and candidate is not None and self.calibration is not None and len(self._foot_points) >= 3:
            try:
                self._board_result = render_board_projection_image(
                    candidate.frame_bgr,
                    self.calibration,
                    self._foot_points,
                    self._foot_confidence,
                    show_overlays=visible,
                )
            except (ValueError, cv2.error):
                pass
        self._render_result("board")
        self._render_result("overhead")
        self.status_var.set(
            self._text("Digital outlines shown.", "Digitální obrysy zobrazeny.")
            if visible
            else self._text("Digital outlines hidden.", "Digitální obrysy skryty.")
        )

    def _toggle_debug_overlay(self) -> None:
        self._render_source()

    def _confirm_frame(self) -> None:
        candidate = self._current()
        if candidate is None or self._closed:
            return
        if self._state == "projection_workspace":
            self._state = "analysing_frame"
            self._set_edit_layer(None)
            self._invalidate_results()
        self.selection_page.grid_remove()
        self.workspace_page.grid_remove()
        self.manual_setup_button.pack_forget()
        self._analysis_failure = None
        self._cancel_work()
        self._generation += 1; generation = self._generation
        cancel = Event(); self._cancel = cancel
        self._state = "analysing_frame"
        # Show the final comparison immediately: the original frame is
        # available now while the computed panel remains in a waiting state.
        self._open_split_review()
        self._analysis_dialog = ProjectionProgressDialog(self.window, self.palette, self._text("Top-down projection", "Projekce shora"), self._text("Preparing the current frame...", "Připravuji aktuální snímek..."), self._cancel_analysis)
        if self._analysis_dialog is not None:
            self._analysis_dialog.close()
            self._analysis_dialog = None
        frame = candidate.frame_bgr.copy(); references = tuple(frame.copy() for frame in self.reference_frames)
        prior = self.calibration; roi = self.roi; signature = self.camera_signature
        cached = self._candidate_estimates.get(candidate.frame_index)
        def worker() -> None:
            board: tuple[tuple[float, float], ...] | None = None
            foul: tuple[tuple[float, float], ...] | None = None
            failure_layer = "board"
            try:
                self._queue.put((generation, "analysis_progress", (12, "tracing_board")))
                if cancel.is_set(): raise ReconstructionCancelled()
                if prior is not None:
                    board = tuple((x * frame.shape[1], y * frame.shape[0]) for x, y in prior.board_corners)
                if board is None:
                    board = detect_board_corners(frame, roi)
                if board is None: raise ValueError(self._text("The board edges could not be located in this frame.", "V tomto snímku se nepodařilo najít hrany prkna."))
                failure_layer = "foul"
                self._queue.put((generation, "analysis_progress", (38, "locating_foul")))
                if cancel.is_set(): raise ReconstructionCancelled()
                foul = tuple((x * frame.shape[1], y * frame.shape[0]) for x, y in prior.foul_line) if prior is not None else detect_foul_line(frame, board)
                if foul is None: raise ValueError(self._text("The foul line could not be located reliably.", "Odrazovou čáru se nepodařilo spolehlivě najít."))
                self._queue.put((generation, "analysis_progress", (58, "correcting_lens")))
                calibration = create_projection_calibration(board, foul, (frame.shape[1], frame.shape[0]), signature, prior)
                failure_layer = "shoe"
                if not calibration.camera_profile:
                    automatic_profile = estimate_radial_profile_from_board_edges(frame, board)
                    if automatic_profile is not None:
                        calibration = replace(calibration, camera_profile=automatic_profile)
                if cancel.is_set(): raise ReconstructionCancelled()
                estimates = [estimate_foot_polygon(frame, references, roi, calibration.board_corners, calibration.foul_line, calibration), cached]
                # Median backgrounds are normally strongest, but a single clean
                # frame before or after take-off can separate the sole better
                # when the whole shortlist still contains the athlete.
                for reference in references[:3]:
                    if cancel.is_set(): raise ReconstructionCancelled()
                    estimates.append(estimate_foot_polygon(frame, (reference,), roi, calibration.board_corners, calibration.foul_line, calibration))
                alternatives: list[tuple[float, FootEstimate, tuple[tuple[float, float], ...], tuple[float, float]]] = []
                for item in estimates:
                    if item is None or item.confidence < .20:
                        continue
                    outline = smooth_closed_outline(item.polygon_px, 20)
                    metric = project_points_to_board_cm(outline, calibration, (frame.shape[1], frame.shape[0]))
                    rect = cv2.minAreaRect(metric.astype(np.float32))[1]
                    long_side, short_side = max(rect), min(rect)
                    source_rect = cv2.minAreaRect(np.asarray(outline, np.float32))[1]
                    source_long, source_short = max(source_rect), max(.1, min(source_rect))
                    shape_quality = min(1.0, source_short / max(.1, source_long) / .22)
                    area_quality = min(1.0, abs(float(cv2.contourArea(np.asarray(outline, np.float32)))) / max(80.0, source_long*source_short*.55))
                    selection_score = .68*item.confidence + .20*shape_quality + .12*area_quality
                    alternatives.append((selection_score, item, outline, (long_side, short_side)))
                if not alternatives:
                    raise ValueError(self._text("No reliable shoe contact outline was found.", "Nepodařilo se najít spolehlivý kontaktní obrys boty."))
                _selection_score, estimate, shoe, dimensions = max(alternatives, key=lambda item: item[0])
                diagnostics = ["automatic_board", "automatic_foul_line", "curved_shoe_outline"]
                if not (10.0 <= dimensions[0] <= 45.0 and 2.5 <= dimensions[1] <= 19.0):
                    # Do not lock the operator out of the correction workspace.
                    # The outline remains visibly marked as uncertain and can be
                    # repaired with the precision editor before either compute.
                    diagnostics.append(f"outline_size_uncertain={dimensions[0]:.1f}x{dimensions[1]:.1f}cm")
                    estimate = FootEstimate(
                        estimate.polygon_px,
                        min(.35, estimate.confidence),
                        estimate.search_roi_px,
                        estimate.candidate_polygons_px,
                    )
                self._queue.put((generation, "analysis_progress", (88, "tracing_shoe")))
                result = ProjectionAnalysisResult(
                    calibration,
                    tuple(board),
                    tuple(foul),
                    shoe,
                    estimate.confidence,
                    tuple(diagnostics),
                    estimate.search_roi_px,
                    estimate.candidate_polygons_px,
                )
                self._queue.put((generation, "analysis_result", result))
            except ReconstructionCancelled:
                self._queue.put((generation, "analysis_cancelled", None))
            except (ValueError, cv2.error) as exc:
                self._queue.put((generation, "analysis_error", {
                    "message": str(exc),
                    "layer": failure_layer,
                    "board": tuple(board or ()),
                    "foul": tuple(foul or ()),
                }))
            except Exception as exc:
                _LOGGER.exception("Automatic projection analysis failed")
                self._queue.put((generation, "analysis_error", {
                    "message": self._text(f"Automatic analysis failed: {exc}", f"Automatická analýza selhala: {exc}"),
                    "layer": failure_layer,
                    "board": tuple(board or ()),
                    "foul": tuple(foul or ()),
                }))
        Thread(target=worker, name=f"projection-analysis-{self.attempt_id}-{generation}", daemon=True).start()

    def _cancel_analysis(self) -> None:
        # There is no alternate-frame page to return to.  Cancelling before
        # analysis completes simply closes this transient projection window.
        self._cancel_work()
        self._generation += 1
        if self._analysis_dialog: self._analysis_dialog.close(); self._analysis_dialog = None
        self.close()

    @staticmethod
    def _manual_board_guess(frame: np.ndarray, roi: Sequence[float]) -> tuple[tuple[float, float], ...]:
        height, width = frame.shape[:2]
        if len(roi) >= 4:
            x, y, roi_width, roi_height = (float(value) for value in roi[:4])
            if max(abs(x), abs(y), abs(roi_width), abs(roi_height)) <= 1.5:
                x, roi_width = x * width, roi_width * width
                y, roi_height = y * height, roi_height * height
        else:
            x, y, roi_width, roi_height = 0.08 * width, 0.25 * height, 0.84 * width, 0.5 * height
        x0 = max(0.0, min(width - 2.0, x + roi_width * 0.08))
        x1 = max(x0 + 1.0, min(width - 1.0, x + roi_width * 0.92))
        y0 = max(0.0, min(height - 2.0, y + roi_height * 0.30))
        y1 = max(y0 + 1.0, min(height - 1.0, y + roi_height * 0.70))
        return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))

    @staticmethod
    def _manual_foul_guess(board: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
        corners = np.asarray(board, dtype=np.float32).reshape(4, 2)
        edges = [(corners[index], corners[(index + 1) % 4]) for index in range(4)]
        first, second = max(edges, key=lambda edge: float(np.linalg.norm(edge[1] - edge[0])))
        centre = corners.mean(axis=0)
        offset = centre - (first + second) * 0.5
        start, end = first + offset, second + offset
        return ((float(start[0]), float(start[1])), (float(end[0]), float(end[1])))

    def _open_manual_setup(self) -> None:
        candidate = self._current()
        failure = self._analysis_failure
        if candidate is None or failure is None:
            return
        frame = candidate.frame_bgr
        board = tuple(failure.get("board") or ())
        if len(board) != 4:
            board = self._manual_board_guess(frame, self.roi)
        foul = tuple(failure.get("foul") or ())
        if len(foul) != 2:
            foul = self._manual_foul_guess(board)
        try:
            calibration = create_projection_calibration(
                board,
                foul,
                (frame.shape[1], frame.shape[0]),
                self.camera_signature,
                self.calibration,
            )
        except (ValueError, cv2.error):
            return
        cached = self._candidate_estimates.get(candidate.frame_index)
        shoe = smooth_closed_outline(cached.polygon_px, 20) if cached is not None else ()
        layer = str(failure.get("layer") or "foul")
        result = ProjectionAnalysisResult(
            calibration,
            tuple((float(x), float(y)) for x, y in board),
            tuple((float(x), float(y)) for x, y in foul),
            tuple((float(x), float(y)) for x, y in shoe),
            cached.confidence if cached is not None else 0.0,
            ("manual_setup", f"manual_focus={layer}"),
            cached.search_roi_px if cached is not None else (),
            cached.candidate_polygons_px if cached is not None else (),
        )
        self.manual_setup_button.pack_forget()
        self._show_workspace(result)
        self._set_edit_layer(layer if layer in {"board", "foul", "shoe"} else "foul")
        if layer == "foul":
            self.status_var.set(self._text(
                "Set the foul line manually: drag all four red corners onto the calibrated line area, press Done, then Re-analyse.",
                "Nastavte odrazovou čáru ručně: přetáhněte všechny čtyři červené rohy na kalibrovanou oblast čáry, stiskněte Hotovo a potom Znovu analyzovat.",
            ))
        elif layer == "board":
            self.status_var.set(self._text(
                "Set the board manually: drag all four yellow corners, press Done, then correct the foul line.",
                "Nastavte prkno ručně: přetáhněte všechny čtyři žluté rohy, stiskněte Hotovo a potom opravte odrazovou čáru.",
            ))
        else:
            self.status_var.set(self._text(
                "Set the shoe outline manually: drag the green points or click to add points, then press Done.",
                "Nastavte obrys boty ručně: přetáhněte zelené body nebo kliknutím přidejte body a potom stiskněte Hotovo.",
            ))

    def _show_workspace(self, result: ProjectionAnalysisResult) -> None:
        if self._closed:
            return
        self._analysis = result; self.calibration = result.calibration
        self._board_points = list(result.board_points_px); self._foul_points = list(result.foul_points_px); self._foot_points = list(result.shoe_points_px)
        frame_size = (self._current().frame_bgr.shape[1], self._current().frame_bgr.shape[0]) if self._current() is not None else (0, 0)
        if len(self._saved_foul_area) == 4 and frame_size[0] > 1:
            scale = np.asarray(frame_size, np.float32)
            self._foul_area_points = [tuple(map(float, point)) for point in np.asarray(self._saved_foul_area, np.float32) * scale]
        else:
            self._foul_area_points = list(foul_area_from_line_px(self._foul_points, frame_size)) if len(self._foul_points) == 2 else []
        self._foot_confidence = result.shoe_confidence
        self._shoe_search_roi = result.shoe_search_roi_px
        self._shoe_candidate_points = list(result.shoe_candidate_points_px)
        if "manual_setup" not in result.diagnostics:
            self.on_calibration_saved(result.calibration)
        self.selection_page.grid_remove(); self.workspace_page.grid(row=1, column=0, sticky="nsew")
        self._state = "projection_workspace"
        self._invalidate_results()
        self.overhead_compute_button.state(["!disabled"])
        self.status_var.set(self._text(
            "Board calibration ready. Computing the top-down board view...",
            "Kalibrace prkna je připravena. Počítám pohled na prkno shora...",
        ))
        self._render_source()
        if "manual_setup" not in result.diagnostics:
            self.window.after_idle(self._open_split_review)
            self.window.after_idle(lambda: self._compute("board"))

    def _go_back(self) -> None:
        self._cancel_work(); self._generation += 1
        self._set_precision_mode(False)
        self.close()

    def _set_edit_layer(self, layer: str | None) -> None:
        was_editing = self._edit_layer is not None
        self._edit_layer = None if layer is None or self._edit_layer == layer else layer
        self._set_precision_mode(self._edit_layer is not None)
        self._set_edit_toolbar(self._edit_layer is not None)
        english_label = {"board": "board corners", "foul": "foul-line area", "shoe": "shoe outline"}.get(layer, layer)
        czech_label = {"board": "rohy prkna", "foul": "oblast odrazové čáry", "shoe": "obrys boty"}.get(layer, layer)
        if self._edit_layer is None:
            self.status_var.set(self._text("Precision editing off. Projection panels restored.", "Přesné úpravy vypnuty. Panely projekcí obnoveny."))
        else:
            self.status_var.set(self._text(f"Precision mode: editing {english_label}. Drag points; click a shoe edge to add a point; right-click removes it.", f"Režim přesnosti: upravujete {czech_label}. Body táhněte; kliknutím na obrys boty přidáte bod; pravým tlačítkem jej odstraníte."))
        self._render_source()
        if was_editing and self._edit_layer is None and self._state == "projection_workspace" and len(self._foot_points) >= 3:
            self.window.after_idle(lambda: self._compute("overhead"))

    def _set_edit_toolbar(self, active: bool) -> None:
        """Leave only Done and the optional zoom switch visible while editing."""
        if not hasattr(self, "edit_done_button"):
            return
        if active:
            for label in self._toolbar_category_labels:
                label.pack_forget()
            for button in self._toolbar_buttons:
                button.pack_forget()
            for button in self._edit_toolbar_buttons:
                button.pack_forget()
            self.mouse_zoom_checkbutton.pack_forget()
            self.show_outlines_checkbutton.pack_forget()
            self.debug_overlay_checkbutton.pack_forget()
            self.close_button.pack_forget()
            self.split_review_button.pack_forget()
            self.brush_snap_checkbutton.pack_forget()
            self.edit_done_button.pack(side="left", padx=(0, 5))
            self.mouse_zoom_checkbutton.pack(side="left", padx=(2, 8))
            if self._edit_layer == "shoe":
                self.brush_snap_checkbutton.pack(side="left", padx=(0, 8))
        else:
            for label in self._toolbar_category_labels:
                label.pack_forget()
            self.edit_done_button.pack_forget()
            self.mouse_zoom_checkbutton.pack_forget()
            self.show_outlines_checkbutton.pack_forget()
            self.debug_overlay_checkbutton.pack_forget()
            self.brush_snap_checkbutton.pack_forget()
            self.split_review_button.pack_forget()
            for button in self._toolbar_buttons:
                button.pack_forget()
            if self._toolbar_category_labels:
                self._toolbar_category_labels[0].pack(side="left", padx=(0, 4))
                for button in self._toolbar_buttons[:2]:
                    button.pack(side="left", padx=(0, 5))
                self._toolbar_category_labels[1].pack(side="left", padx=(4, 4))
                for button in self._toolbar_buttons[2:5]:
                    button.pack(side="left", padx=(0, 5))
                self._toolbar_category_labels[2].pack(side="left", padx=(4, 4))
                for button in self._toolbar_buttons[5:]:
                    button.pack(side="left", padx=(0, 5))
                self._toolbar_category_labels[3].pack(side="left", padx=(4, 4))
            self.mouse_zoom_checkbutton.pack(side="left", padx=(2, 8))
            self.show_outlines_checkbutton.pack(side="left", padx=(0, 8))
            self.debug_overlay_checkbutton.pack(side="left", padx=(0, 8))
            self.close_button.pack(side="right")
            self.split_review_button.pack(side="right", padx=(0, 5))

    def _set_precision_mode(self, active: bool) -> None:
        """Give point editing the full workspace while keeping the source frame authoritative."""
        if not hasattr(self, "source_canvas"):
            return
        if active:
            self.source_canvas.configure(height=500, cursor="crosshair")
            self.projections_frame.grid_remove()
            self.progress_frame.grid_remove()
            self.workspace_page.rowconfigure(1, weight=1)
            self.workspace_page.rowconfigure(2, weight=0)
        else:
            self.source_canvas.configure(height=220, cursor="tcross" if self.mouse_zoom_var.get() else "arrow")
            self.projections_frame.grid()
            if self._active_compute:
                self.progress_frame.grid()
            else:
                self.progress_frame.grid_remove()
            self.workspace_page.rowconfigure(1, weight=0)
            self.workspace_page.rowconfigure(2, weight=1)
        self.source_canvas.delete("zoom")
        self.window.update_idletasks()
        self._render_source()

    def _frame_to_canvas(self, point: Sequence[float]) -> tuple[float, float]:
        left, top, right, bottom = self._source_bounds; width, height = self._source_frame_size
        return left + float(point[0]) / max(1, width) * (right - left), top + float(point[1]) / max(1, height) * (bottom - top)

    def _canvas_to_frame(self, x: float, y: float) -> tuple[float, float] | None:
        left, top, right, bottom = self._source_bounds; width, height = self._source_frame_size
        if not (left <= x <= right and top <= y <= bottom): return None
        return ((x - left) / max(1.0, right - left) * width, (y - top) / max(1.0, bottom - top) * height)

    def _render_source(self) -> None:
        candidate = self._current(); self.source_canvas.delete("all")
        if candidate is None: return
        frame = candidate.frame_bgr; cw, ch = max(300, self.source_canvas.winfo_width()), max(180, self.source_canvas.winfo_height())
        scale = min((cw - 12) / frame.shape[1], (ch - 12) / frame.shape[0]); rw, rh = int(frame.shape[1] * scale), int(frame.shape[0] * scale)
        left, top = (cw - rw) / 2, (ch - rh) / 2
        self._source_photo = self._photo(frame, (rw, rh)); self.source_canvas.create_image(left, top, image=self._source_photo, anchor="nw")
        self._source_bounds = (left, top, left + rw, top + rh); self._source_frame_size = (frame.shape[1], frame.shape[0])
        for layer, points, color in (("board", self._board_points, "#f5bd4f"), ("foul", self._foul_area_points or self._foul_points, "#ff6675"), ("shoe", self._foot_points, "#70d6a5")):
            if not self.show_outlines_var.get() and not self.debug_overlay_var.get() and layer != self._edit_layer:
                continue
            coords = [value for point in points for value in self._frame_to_canvas(point)]
            if layer in {"board", "foul"} and len(points) >= 4: self.source_canvas.create_polygon(*coords, outline=color, fill="", width=3)
            elif layer == "shoe" and len(points) >= 3: self.source_canvas.create_line(*coords, *self._frame_to_canvas(points[0]), fill=color, width=3, smooth=True, splinesteps=16)
            elif len(points) >= 2: self.source_canvas.create_line(*coords, fill=color, width=3)
            if self._edit_layer == layer:
                for index, point in enumerate(points):
                    x, y = self._frame_to_canvas(point); self.source_canvas.create_oval(x-5, y-5, x+5, y+5, fill=color, outline="#111722")
                    self.source_canvas.create_text(x+8, y-8, text=str(index+1), fill=color, anchor="sw")
        if self.debug_overlay_var.get():
            if len(self._shoe_search_roi) == 4:
                x0, y0, x1, y1 = self._shoe_search_roi
                left_top = self._frame_to_canvas((x0, y0)); right_bottom = self._frame_to_canvas((x1, y1))
                self.source_canvas.create_rectangle(*left_top, *right_bottom, outline="#6db4ff", width=2, dash=(7, 4), tags="debug")
                self.source_canvas.create_text(left_top[0] + 5, left_top[1] + 5, text="shoe search ROI", fill="#6db4ff", anchor="nw", tags="debug")
            for candidate_points in self._shoe_candidate_points:
                if len(candidate_points) < 3:
                    continue
                candidate_coords = [value for point in candidate_points for value in self._frame_to_canvas(point)]
                self.source_canvas.create_line(*candidate_coords, *self._frame_to_canvas(candidate_points[0]), fill="#ef9b55", width=2, dash=(4, 3), tags="debug")
        if self.debug_overlay_var.get() and len(self._foot_points) >= 3:
            values = np.asarray(self._foot_points, dtype=np.float32)
            centre = values.mean(axis=0)
            _mean, _eigenvalues, eigenvectors = cv2.PCACompute2(values, mean=None)
            axis = eigenvectors[0]
            span = max(20.0, float(np.ptp(values, axis=0).max()))
            start, end = centre - axis * span * .65, centre + axis * span * .65
            self.source_canvas.create_line(*self._frame_to_canvas(start), *self._frame_to_canvas(end), fill="#f2cf62", width=2, dash=(5, 3), tags="debug")
            toe = end
            heel = start
            if len(self._foul_points) == 2 and _line_distance(start, np.asarray(self._foul_points, np.float32)) < _line_distance(end, np.asarray(self._foul_points, np.float32)):
                toe, heel = start, end
            for point, label in ((heel, "heel"), (toe, "toe")):
                px, py = self._frame_to_canvas(point)
                self.source_canvas.create_oval(px - 4, py - 4, px + 4, py + 4, fill="#f2cf62", outline="#111722", tags="debug")
                self.source_canvas.create_text(px + 7, py - 5, text=label, fill="#f2cf62", anchor="sw", tags="debug")

    def _source_press(self, event) -> str:
        if self._edit_layer is None: return "break"
        point = self._canvas_to_frame(event.x, event.y)
        if point is None: return "break"
        points = self._editable_layer_points()
        if self._edit_layer == "shoe" and self.brush_snap_var.get():
            self._brush_trace = [point]
            self._drag_index = None
            return "break"
        self._drag_index = next((i for i, existing in enumerate(points) if math.hypot(existing[0]-point[0], existing[1]-point[1]) < 30), None)
        if self._drag_index is None and self._edit_layer == "shoe" and len(points) < 3:
            points.append(point); self._drag_index = len(points) - 1; self._render_source(); self._invalidate_results()
        elif self._drag_index is None and self._edit_layer == "shoe" and len(points) < 32:
            best_index = min(range(len(points)), key=lambda i: _line_distance(np.asarray(point, np.float32), np.asarray((points[i], points[(i+1)%len(points)]), np.float32)))
            points.insert(best_index + 1, point); self._drag_index = best_index + 1; self._render_source(); self._invalidate_results()
        return "break"

    def _source_drag(self, event) -> str:
        if self._edit_layer == "shoe" and self.brush_snap_var.get() and self._brush_trace:
            point = self._canvas_to_frame(event.x, event.y)
            if point is not None and math.hypot(point[0]-self._brush_trace[-1][0], point[1]-self._brush_trace[-1][1]) >= 3:
                self._brush_trace.append(point)
                self._render_source()
                coords = [value for item in self._brush_trace for value in self._frame_to_canvas(item)]
                self.source_canvas.create_line(*coords, fill="#d9f7e8", width=3, smooth=True, tags="brush")
                if self.mouse_zoom_var.get(): self._source_hover(event)
            return "break"
        if self._drag_index is None or self._edit_layer is None: return "break"
        point = self._canvas_to_frame(event.x, event.y)
        if point is None: return "break"
        points = self._editable_layer_points()
        points[self._drag_index] = point
        self._render_source()
        if self.mouse_zoom_var.get():
            self._source_hover(event)
        return "break"

    def _source_release(self, _event) -> str:
        if self._edit_layer == "shoe" and self.brush_snap_var.get() and len(self._brush_trace) >= 3:
            candidate = self._current()
            if candidate is not None:
                snapped = snap_brush_trace_to_edges(candidate.frame_bgr, self._brush_trace)
                if len(snapped) >= 3:
                    self._foot_points = list(snapped)
                    self._foot_confidence = max(self._foot_confidence, .72)
            self._brush_trace.clear()
            self._render_source(); self._invalidate_results()
            self.status_var.set(self._text("Brush trace snapped to the nearest shoe edges. Adjust individual points if needed.", "Tah štětce byl přichycen k nejbližším hranám boty. V případě potřeby upravte jednotlivé body."))
            return "break"
        if self._drag_index is not None:
            changed_layer = self._edit_layer
            self._drag_index = None
            if changed_layer in {"board", "foul"}:
                self._update_calibration_from_edits()
            self._invalidate_results()
        return "break"

    def _source_remove_point(self, event) -> str:
        if self._edit_layer != "shoe" or len(self._foot_points) <= 3: return "break"
        point = self._canvas_to_frame(event.x, event.y)
        if point is None: return "break"
        index = min(range(len(self._foot_points)), key=lambda i: math.hypot(self._foot_points[i][0]-point[0], self._foot_points[i][1]-point[1]))
        if math.hypot(self._foot_points[index][0]-point[0], self._foot_points[index][1]-point[1]) < 45:
            self._foot_points.pop(index); self._render_source(); self._invalidate_results()
        return "break"

    def _update_calibration_from_edits(self) -> None:
        if len(self._foul_area_points) == 4:
            self._foul_points = list(foul_line_from_area_px(self._foul_area_points, self._board_points))
        if len(self._board_points) != 4 or len(self._foul_points) != 2: return
        try:
            self.calibration = create_projection_calibration(self._board_points, self._foul_points, self._source_frame_size, self.camera_signature, self.calibration)
            self.on_calibration_saved(self.calibration)
            if self.on_foul_area_saved is not None and self._source_frame_size[0] > 1 and len(self._foul_area_points) == 4:
                scale = np.asarray(self._source_frame_size, np.float32)
                normalized = np.asarray(self._foul_area_points, np.float32) / scale
                self._saved_foul_area = tuple((float(x), float(y)) for x, y in normalized)
                self.on_foul_area_saved(self._saved_foul_area)
        except ValueError as exc:
            self.status_var.set(str(exc))

    def _editable_layer_points(self) -> list[tuple[float, float]]:
        if self._edit_layer == "board":
            return self._board_points
        if self._edit_layer == "foul":
            return self._foul_area_points if len(self._foul_area_points) == 4 else self._foul_points
        return self._foot_points

    def _invalidate_results(self) -> None:
        self._cancel_work(); self._generation += 1
        self._board_result = None; self._overhead_result = None; self._active_compute = None
        if hasattr(self, "board_canvas"):
            self.split_review_button.state(["disabled"])
            self.board_compute_button.configure(text=self._text("Compute", "Vypočítat")); self.overhead_compute_button.configure(text=self._text("Compute", "Vypočítat"))
            self.board_compute_button.state(["!disabled"]); self.overhead_compute_button.state(["!disabled"])
            self.reconstruction_progress.configure(value=0); self.progress_label_var.set("")
            self.progress_frame.grid_remove()
            if hasattr(self, "result_badge_var"):
                self.result_badge_var.set(self._text("WAITING", "ČEKÁ")); self.result_confidence_var.set("")
                self.result_badge.configure(bg=self.palette["surface2"], fg=self.palette["muted"])
            self._render_result("board"); self._render_result("overhead")

    def _compute(self, target: str) -> None:
        candidate = self._current()
        if self._active_compute:
            self.status_var.set(self._text("A projection is already being computed.", "Projekce se již počítá."))
            return
        if candidate is None:
            self.status_var.set(self._text("No source frame is available.", "Zdrojový snímek není k dispozici."))
            return
        if self.calibration is None:
            self.status_var.set(self._text("Board calibration is missing. Edit the board and foul line first.", "Chybí kalibrace prkna. Nejprve upravte prkno a odrazovou čáru."))
            return
        if len(self._foot_points) < 3 and target != "board":
            self.status_var.set(self._text("No usable shoe outline was found. Edit the shoe outline before computing.", "Nebyl nalezen použitelný obrys boty. Před výpočtem upravte obrys boty."))
            return
        self._cancel_work(); self._generation += 1; generation = self._generation
        cancel = Event(); self._cancel = cancel; self._active_compute = target
        if target == "board":
            self._board_result = None
        else:
            self._overhead_result = None
        self.board_compute_button.state(["disabled"]); self.overhead_compute_button.state(["disabled"])
        active_button = self.board_compute_button if target == "board" else self.overhead_compute_button
        active_button.configure(text=self._text("Computing...", "Počítám..."))
        self._compute_started_at = time.perf_counter()
        self.reconstruction_progress.configure(value=2)
        self.progress_label_var.set(self._text("Preparing projection...", "Připravuji projekci..."))
        self.progress_frame.grid()
        frame = candidate.frame_bgr.copy(); calibration = self.calibration; outline = tuple(self._foot_points)
        show_outlines = bool(self.show_outlines_var.get())
        observations = tuple(
            (item.frame_index, item.frame_bgr.copy())
            for item in self.candidates
            if abs(item.frame_index - candidate.frame_index) <= 1
            and abs(item.timestamp_ns - candidate.timestamp_ns) <= 300_000_000
        ); references = tuple(frame.copy() for frame in self.reference_frames)
        def worker() -> None:
            def report(stage: str, value: int) -> None: self._queue.put((generation, "compute_progress", (target, stage, value)))
            try:
                if target == "board":
                    report("rectifying_board", 20)
                    if cancel.is_set(): raise ReconstructionCancelled()
                    image = render_board_projection_image(frame, calibration, (), 0.0, show_overlays=show_outlines)
                    report("rendering", 90)
                    self._queue.put((generation, "board_result", image))
                else:
                    result = reconstruct_shoe_overhead(frame, outline, observations, references, calibration, time_limit_seconds=5.0, cancel=cancel, progress=report)
                    self._queue.put((generation, "overhead_result", result))
            except ReconstructionCancelled: self._queue.put((generation, "compute_cancelled", target))
            except ReconstructionTimedOut: self._queue.put((generation, "compute_error", (target, self._text("The top-down reconstruction exceeded five seconds.", "Rekonstrukce shora překročila pět sekund."))))
            except (ValueError, cv2.error) as exc: self._queue.put((generation, "compute_error", (target, str(exc))))
            except Exception as exc: self._queue.put((generation, "compute_error", (target, f"Projection failed: {exc}")))
        Thread(target=worker, name=f"projection-{target}-{self.attempt_id}-{generation}", daemon=True).start()

    def _poll_queue(self) -> None:
        if self._closed: return
        labels = {
            "preparing_frames": self._text("Preparing frames...", "Připravuji snímky..."), "isolating_shoe": self._text("Isolating the shoe...", "Odděluji botu..."),
            "fitting_model": self._text("Fitting the model...", "Přizpůsobuji model..."), "rectifying_board": self._text("Flattening the board...", "Vyrovnávám prkno..."),
            "rendering": self._text("Rendering...", "Vykresluji..."), "complete": self._text("Projection ready.", "Projekce je připravena."),
        }
        analysis_labels = {
            "correcting_lens": self._text("Correcting lens distortion...", "Opravuji zkreslení objektivu..."),
            "tracing_board": self._text("Tracing board edges...", "Vyhledávám hrany prkna..."),
            "locating_foul": self._text("Locating the foul line...", "Vyhledávám odrazovou čáru..."),
            "tracing_shoe": self._text("Tracing the shoe contact edge...", "Vyhledávám kontaktní obrys boty..."),
        }
        try:
            while True:
                generation, kind, payload = self._queue.get_nowait()
                if generation != self._generation: continue
                if kind == "analysis_progress":
                    value, stage = payload
                    label = analysis_labels.get(str(stage), str(stage))
                    if self._analysis_dialog:
                        self._analysis_dialog.update(value, label)
                    # Analysis occupies the first 40% of the single review
                    # bar; reconstruction owns the remaining 60%.
                    self._update_split_review_progress(float(value) * 0.4, label)
                elif kind == "analysis_result":
                    if self._analysis_dialog: self._analysis_dialog.complete(self._text("Analysis complete.", "Analýza je dokončena.")); self._analysis_dialog.close(); self._analysis_dialog = None
                    self._cancel = None; self._show_workspace(payload)
                elif kind in {"analysis_cancelled", "analysis_error"}:
                    if kind == "analysis_error" and isinstance(payload, dict) and str(payload.get("layer") or "") == "shoe":
                        message = str(payload.get("message") or "Shoe detection failed.")
                        if self._analysis_dialog:
                            self._analysis_dialog.close()
                            self._analysis_dialog = None
                        self._cancel = None
                        self._analysis_failure = dict(payload)
                        board = tuple(payload.get("board") or ())
                        foul = tuple(payload.get("foul") or ())
                        candidate = self._current()
                        if candidate is not None and len(board) == 4 and len(foul) == 2:
                            # Shoe detection is decision support, not a
                            # prerequisite for flattening the calibrated board.
                            frame_size = (candidate.frame_bgr.shape[1], candidate.frame_bgr.shape[0])
                            calibration = create_projection_calibration(board, foul, frame_size, self.camera_signature, self.calibration)
                            fallback = ProjectionAnalysisResult(
                                calibration,
                                board,
                                foul,
                                (),
                                0.0,
                                ("automatic_board", "automatic_foul_line", "shoe_detection_failed"),
                                (),
                                (),
                            )
                            self._show_workspace(fallback)
                            self.status_var.set(self._text(
                                "Shoe detection failed; the calibrated board projection is still available.",
                                "Detekce boty selhala; kalibrovaná projekce prkna je stále k dispozici.",
                            ))
                        else:
                            self._state = "projection_unavailable"
                            self.manual_setup_button.pack_forget()
                            self._update_split_review_unavailable(message)
                            self.status_var.set(message)
                        continue
                    self._close_split_review()
                    if self._analysis_dialog: self._analysis_dialog.close(); self._analysis_dialog = None
                    self._cancel = None; self._state = "selecting_frame"
                    self.workspace_page.grid_remove()
                    if kind == "analysis_error":
                        failure = payload if isinstance(payload, dict) else {"message": str(payload), "layer": "foul", "board": (), "foul": ()}
                        self._analysis_failure = failure
                        message = str(failure.get("message") or self._text("Automatic analysis failed.", "Automatická analýza selhala."))
                        layer = str(failure.get("layer") or "foul")
                        manual_labels = {
                            "board": self._text("Set board manually", "Nastavit prkno ručně"),
                            "foul": self._text("Set foul line manually", "Nastavit odrazovou čáru ručně"),
                            "shoe": self._text("Set shoe outline manually", "Nastavit obrys boty ručně"),
                        }
                        self.manual_setup_button.configure(text=manual_labels.get(layer, self._text("Set up manually", "Nastavit ručně")))
                        guidance = self._text(
                            " Use the manual button below to continue with this frame.",
                            " Pokračujte s tímto snímkem pomocí tlačítka ručního nastavení níže.",
                        )
                        self.selection_canvas.delete("message")
                        self.selection_canvas.create_text(
                            20,
                            self.selection_canvas.winfo_height()-20,
                            text=message + guidance,
                            fill="#ff8a96",
                            anchor="sw",
                            width=max(240, self.selection_canvas.winfo_width()-40),
                            tags="message",
                        )
                        self.manual_setup_button.pack(side="left", padx=(0, 6), before=self.confirm_frame_button)
                        self._open_manual_setup()
                        self.status_var.set(message)
                elif kind == "compute_progress":
                    _target, stage, value = payload
                    label = labels.get(stage, stage)
                    self.progress_label_var.set(label)
                    self.reconstruction_progress.configure(value=max(float(self.reconstruction_progress["value"]), min(99, value)))
                    self._update_split_review_progress(40.0 + float(value) * 0.6, label)
                elif kind == "board_result":
                    self._board_result = payload; self._finish_compute("board")
                elif kind == "overhead_result":
                    self._overhead_result = payload; self._finish_compute("overhead")
                elif kind == "compute_error":
                    target, message = payload; self._finish_compute(target, message)
                elif kind == "compute_cancelled": self._finish_compute(str(payload), self._text("Calculation cancelled.", "Výpočet byl zrušen."))
        except Empty:
            pass
        except Exception as exc:
            # A Tk/Pillow display failure must not kill the only queue poller;
            # otherwise all later projection jobs complete invisibly and both
            # Compute controls appear permanently stuck.
            _LOGGER.exception("Projection result queue handler failed")
            target = self._active_compute
            self._cancel = None
            self._active_compute = None
            if hasattr(self, "board_compute_button"):
                self.board_compute_button.state(["!disabled"])
                self.overhead_compute_button.state(["!disabled"])
            message = self._text(
                f"Projection display failed: {exc}",
                f"Zobrazení projekce selhalo: {exc}",
            )
            self.status_var.set(message)
            self.progress_label_var.set(message)
            if target in {"board", "overhead"}:
                button = self.board_compute_button if target == "board" else self.overhead_compute_button
                button.configure(text=self._text("Try again", "Zkusit znovu"))
        finally:
            if not self._closed:
                try:
                    self.window.after(40, self._poll_queue)
                except tk.TclError:
                    pass

    def _finish_compute(self, target: str, error: str = "") -> None:
        self._cancel = None; self._active_compute = None
        self.board_compute_button.state(["!disabled"]); self.overhead_compute_button.state(["!disabled"])
        if error:
            self.status_var.set(error); self.progress_label_var.set(error)
            (self.board_compute_button if target == "board" else self.overhead_compute_button).configure(text=self._text("Try again", "Zkusit znovu"))
            self.progress_frame.grid_remove()
            if target == "overhead":
                self._update_split_review_error(error)
        else:
            self._last_compute_duration_ms = max(0.0, (time.perf_counter() - self._compute_started_at) * 1000.0)
            self.reconstruction_progress.configure(value=100)
            self.progress_label_var.set(self._text("Projection ready.", "Projekce je připravena."))
            self.status_var.set(self._text(
                f"Projection ready • {self._last_compute_duration_ms:.0f} ms",
                f"Projekce připravena • {self._last_compute_duration_ms:.0f} ms",
            ))
            self.progress_frame.grid_remove()
            if target == "board" and self._board_result is not None:
                automatic = self._automatic_verdict_display()
                if automatic is not None:
                    badge, colour, confidence = automatic
                    self.result_badge_var.set(badge)
                    self.result_confidence_var.set(self._text(
                        f"Confidence {confidence:.0%}",
                        f"Spolehlivost {confidence:.0%}",
                    ))
                    strong = getattr(self, "automatic_advisory_status", "") in {"valid", "foul"}
                    self.result_badge.configure(bg=colour, fg="#ffffff" if strong else "#111722")
                else:
                    self.result_badge_var.set(self._text("BOARD VIEW", "POHLED NA PRKNO"))
                    self.result_confidence_var.set("")
                    self.result_badge.configure(bg=self.palette["accent"], fg="#111722")
                self._update_split_review_result()
        self._render_result(target)
        if target == "board":
            self._render_result("overhead")
        self.split_review_button.state(["!disabled"] if self._board_result is not None else ["disabled"])
        if not error and target == "board" and self._board_result is not None:
            self.window.after_idle(self._open_split_review)
    def _source_review_image(self) -> np.ndarray | None:
        candidate = self._current()
        if candidate is None:
            return None
        image = candidate.frame_bgr.copy()
        if not self.show_outlines_var.get():
            return image
        def polyline(points: Sequence[Sequence[float]], colour: tuple[int, int, int], closed: bool = True) -> None:
            if len(points) < 2:
                return
            values = np.rint(np.asarray(points, dtype=np.float32)).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(image, [values], closed, colour, 4, cv2.LINE_AA)
        polyline(self._board_points, (80, 190, 245))
        polyline(self._foul_area_points or self._foul_points, (70, 80, 245), closed=len(self._foul_area_points) >= 4)
        polyline(self._foot_points, (95, 220, 150))
        return image

    @staticmethod
    def _fit_review_image(canvas: tk.Canvas, image: np.ndarray | None, photo_holder: list[ImageTk.PhotoImage], empty_text: str = "No image") -> None:
        canvas.delete("all")
        if image is None or image.size == 0:
            canvas.create_text(max(20, canvas.winfo_width() / 2), max(20, canvas.winfo_height() / 2), text=empty_text, fill="#b8c5d2", width=max(220, canvas.winfo_width() - 40))
            return
        width, height = max(1, canvas.winfo_width() - 18), max(1, canvas.winfo_height() - 18)
        image_height, image_width = image.shape[:2]
        scale = min(width / max(1, image_width), height / max(1, image_height))
        shown = cv2.resize(image, (max(1, int(image_width * scale)), max(1, int(image_height * scale))), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)))
        photo_holder[:] = [photo]
        canvas.create_image(canvas.winfo_width() / 2, canvas.winfo_height() / 2, image=photo, anchor="center")

    def _show_split_review_again(self) -> None:
        if self._split_review_window is not None:
            try:
                self._split_review_window.lift()
                self._split_review_window.focus_force()
            except tk.TclError:
                pass
            return
        if self._overhead_result is None and self._board_result is None:
            self.status_var.set(self._text("No computed projection is available yet.", "Zatím není k dispozici žádná vypočtená projekce."))
            return
        self._open_split_review()

    def _open_split_review(self) -> None:
        if self._closed or (self._overhead_result is None and self._board_result is None) or self._split_review_window is not None:
            return
        original = self._source_review_image()
        if original is None:
            self.status_var.set(self._text("Could not open the comparison: the source frame is unavailable.", "Nelze otevřít porovnání: zdrojový snímek není k dispozici."))
            return
        result = self._overhead_result.overhead_image if self.show_outlines_var.get() or self._overhead_result.clean_overhead_image is None else self._overhead_result.clean_overhead_image
        review = tk.Toplevel(self.window)
        self._split_review_window = review
        review.title(self._text("Top-down projection review", "Kontrola projekce shora"))
        review.configure(bg="#0b1118")
        review.attributes("-fullscreen", True)
        review.protocol("WM_DELETE_WINDOW", self._close_split_review)
        review.bind("<KeyPress>", self._close_split_review)
        review.bind("<Escape>", self._close_split_review)
        review.rowconfigure(1, weight=1); review.columnconfigure(0, weight=1); review.columnconfigure(1, weight=1)
        header = tk.Frame(review, bg="#111a24", padx=18, pady=12)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(header, text=self._text("TOP-DOWN PROJECTION REVIEW", "KONTROLA PROJEKCE SHORA"), bg="#111a24", fg="#f2f6fa", font=("Segoe UI", 18, "bold")).pack(side="left")
        status = self._overhead_result.verdict_status
        badge = projection_verdict_text(status)
        colour = "#ff6474" if status == "over" else "#70d6a5" if status == "clear" else "#f3c969"
        tk.Label(header, text=badge, bg=colour, fg="#101820", padx=14, pady=4, font=("Segoe UI", 15, "bold")).pack(side="left", padx=(20, 8))
        tk.Label(header, text=self._text(f"Confidence {self._overhead_result.fit_confidence:.0%}  •  Press any key to close", f"Spolehlivost {self._overhead_result.fit_confidence:.0%}  •  Stisknutím klávesy zavřete"), bg="#111a24", fg="#b8c5d2", font=("Segoe UI", 11)).pack(side="right")
        left_frame = tk.Frame(review, bg="#0b1118", padx=12, pady=10); left_frame.grid(row=1, column=0, sticky="nsew")
        right_frame = tk.Frame(review, bg="#0b1118", padx=12, pady=10); right_frame.grid(row=1, column=1, sticky="nsew")
        tk.Label(left_frame, text=self._text("Original camera frame", "Původní snímek kamery"), bg="#0b1118", fg="#d8e2ed", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        tk.Label(right_frame, text=self._text("Computed top-down view", "Vypočtený pohled shora"), bg="#0b1118", fg="#d8e2ed", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        left_canvas = tk.Canvas(left_frame, bg="#05080c", highlightthickness=1, highlightbackground="#31404e")
        right_canvas = tk.Canvas(right_frame, bg="#05080c", highlightthickness=1, highlightbackground="#31404e")
        left_canvas.pack(fill="both", expand=True); right_canvas.pack(fill="both", expand=True)
        self._split_review_photos = []
        def render(_event=None) -> None:
            holders = getattr(render, "holders", None)
            if holders is None:
                holders = [[], []]; render.holders = holders
            self._fit_review_image(left_canvas, original, holders[0])
            self._fit_review_image(right_canvas, result, holders[1])
            self._split_review_photos = holders[0] + holders[1]
        bind_resize_only(left_canvas, render); bind_resize_only(right_canvas, render)
        review.after_idle(lambda: (review.focus_force(), render()))

    def _open_split_review(self) -> None:
        """Open the final two-panel review before reconstruction completes."""
        if self._closed or self._split_review_window is not None:
            return
        original = self._source_review_image()
        if original is None:
            self.status_var.set(self._text("Could not open the comparison: the source frame is unavailable.", "Zdrojový snímek není k dispozici."))
            return
        review = tk.Toplevel(self.window)
        self._split_review_window = review
        review.title(self._text("Top-down projection review", "Kontrola projekce shora"))
        review.configure(bg="#0b1118")
        review.attributes("-fullscreen", True)
        review.protocol("WM_DELETE_WINDOW", self._close_split_review)
        review.bind("<KeyPress>", self._close_split_review)
        review.bind("<Escape>", self._close_split_review)
        review.rowconfigure(1, weight=1); review.columnconfigure(0, weight=1); review.columnconfigure(1, weight=1)
        header = tk.Frame(review, bg="#111a24", padx=18, pady=12)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        tk.Label(header, text=self._text("TOP-DOWN PROJECTION REVIEW", "KONTROLA PROJEKCE SHORA"), bg="#111a24", fg="#f2f6fa", font=("Segoe UI", 18, "bold")).pack(side="left")
        self._split_review_badge = tk.Label(header, text="COMPUTING", bg="#f3c969", fg="#101820", padx=14, pady=4, font=("Segoe UI", 13, "bold"))
        self._split_review_badge.pack(side="left", padx=(20, 8))
        self._split_review_detail = tk.Label(header, text=self._text("Original frame is ready; waiting for the computed projection.", "Původní snímek je připraven; čekám na projekci."), bg="#111a24", fg="#b8c5d2", font=("Segoe UI", 10))
        self._split_review_detail.pack(side="left", padx=(0, 12))
        self._split_review_stage_var = tk.StringVar(value=self._text("Preparing projection...", "Připravuji projekci..."))
        ttk.Label(header, textvariable=self._split_review_stage_var, style="Muted.TLabel").pack(side="right", padx=(8, 8))
        self._split_review_progress = ttk.Progressbar(header, mode="determinate", maximum=100, value=0, length=220, style="Modal.Horizontal.TProgressbar")
        self._split_review_progress.pack(side="right")
        left_frame = tk.Frame(review, bg="#0b1118", padx=12, pady=10); left_frame.grid(row=1, column=0, sticky="nsew")
        right_frame = tk.Frame(review, bg="#0b1118", padx=12, pady=10); right_frame.grid(row=1, column=1, sticky="nsew")
        tk.Label(left_frame, text=self._text("Original camera frame", "Původní snímek kamery"), bg="#0b1118", fg="#d8e2ed", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        tk.Label(right_frame, text=self._text("Computed top-down view", "Vypočtený pohled shora"), bg="#0b1118", fg="#d8e2ed", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 5))
        left_canvas = tk.Canvas(left_frame, bg="#05080c", highlightthickness=1, highlightbackground="#31404e")
        right_canvas = tk.Canvas(right_frame, bg="#05080c", highlightthickness=1, highlightbackground="#31404e")
        left_canvas.pack(fill="both", expand=True); right_canvas.pack(fill="both", expand=True)
        self._split_review_photos = []
        def render(_event=None) -> None:
            holders = getattr(render, "holders", None)
            if holders is None:
                holders = [[], []]; render.holders = holders
            result = self._board_result
            if self._split_review_reveal_image is not None:
                result = self._split_review_reveal_image
            # Animation frames only replace the small computed raster. Avoid
            # repeatedly scaling the large authoritative camera image.
            if _event is not None or not holders[0]:
                self._fit_review_image(left_canvas, original, holders[0])
            self._fit_review_image(right_canvas, result, holders[1], self._text("Waiting for top-down board view...", "Čekám na pohled na prkno shora..."))
            self._split_review_photos = holders[0] + holders[1]
        self._split_review_render = render
        bind_resize_only(left_canvas, render); bind_resize_only(right_canvas, render)
        review.after_idle(lambda: (review.focus_force(), render()))
        if self._overhead_result is not None or self._board_result is not None:
            self._update_split_review_result()

    def _update_split_review_progress(self, value: float, label: str) -> None:
        if self._split_review_progress is not None:
            self._split_review_progress.configure(value=max(float(self._split_review_progress["value"]), min(99.0, float(value))))
        if self._split_review_stage_var is not None:
            self._split_review_stage_var.set(label)

    def _update_split_review_result(self) -> None:
        final_image = self._board_result
        if final_image is None:
            return
        automatic = self._automatic_verdict_display()
        if automatic is not None:
            badge, colour, confidence = automatic
            detail = self._text(f"Confidence {confidence:.0%}", f"Spolehlivost {confidence:.0%}")
        else:
            badge = self._text("BOARD VIEW", "POHLED NA PRKNO")
            colour = self.palette["accent"]
            confidence = 1.0
            detail = self._text("Calibrated top-down board view", "Kalibrovaný pohled na prkno shora")
        if _client_animations_enabled() and self._split_review_window is not None and automatic is not None:
            if self._split_review_stage_var is not None:
                self._split_review_stage_var.set(self._text("Projection ready.", "Projekce je připravena."))
            if self._split_review_progress is not None:
                self._split_review_progress.configure(value=100)
                self._split_review_progress.pack_forget()
            self._start_split_review_reveal(final_image, badge, colour, confidence)
            return
        if self._split_review_badge is not None:
            self._split_review_badge.configure(text=badge, bg=colour, fg="#101820")
        if self._split_review_detail is not None:
            self._split_review_detail.configure(text=detail, fg="#b8c5d2")
        if self._split_review_stage_var is not None:
            self._split_review_stage_var.set(self._text("Board view ready.", "Pohled na prkno je připraven."))
        if self._split_review_progress is not None:
            self._split_review_progress.configure(value=100)
            self._split_review_progress.pack_forget()
        if self._split_review_render is not None:
            self._split_review_render()
    @staticmethod
    def _blend_hex(first: str, second: str, amount: float) -> str:
        progress = max(0.0, min(1.0, float(amount)))
        start = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
        end = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
        values = tuple(round(a + (b - a) * progress) for a, b in zip(start, end))
        return "#%02x%02x%02x" % values

    def _start_split_review_reveal(self, final_image: np.ndarray, badge: str, colour: str, confidence: float) -> None:
        """Fade completed pixels, then the existing result text, without blocking Tk."""
        if self._split_review_animation_job is not None:
            try:
                self.window.after_cancel(self._split_review_animation_job)
            except tk.TclError:
                pass
            self._split_review_animation_job = None
        final = np.ascontiguousarray(final_image)
        base = np.empty_like(final)
        base[:] = (12, 17, 24)
        image_started = time.perf_counter()

        def image_step() -> None:
            if self._closed or self._split_review_window is None:
                self._split_review_animation_job = None
                return
            progress = min(1.0, (time.perf_counter() - image_started) * 1000.0 / 220.0)
            eased = _strong_ease_out(progress)
            self._split_review_reveal_image = cv2.addWeighted(final, eased, base, 1.0 - eased, 0)
            if self._split_review_render is not None:
                self._split_review_render()
            if progress < 1.0:
                self._split_review_animation_job = self.window.after(16, image_step)
                return
            self._split_review_reveal_image = None
            if self._split_review_badge is not None:
                self._split_review_badge.configure(text=badge, bg="#111a24", fg="#111a24")
            if self._split_review_detail is not None:
                self._split_review_detail.configure(
                    text=self._text(f"Confidence {confidence:.0%}", f"Spolehlivost {confidence:.0%}"),
                    fg="#111a24",
                )

            def begin_text() -> None:
                text_started = time.perf_counter()

                def text_step() -> None:
                    if self._closed or self._split_review_window is None:
                        self._split_review_animation_job = None
                        return
                    progress = min(1.0, (time.perf_counter() - text_started) * 1000.0 / 160.0)
                    eased = _strong_ease_out(progress)
                    if self._split_review_badge is not None:
                        self._split_review_badge.configure(
                            bg=self._blend_hex("#111a24", colour, eased),
                            fg=self._blend_hex("#111a24", "#101820", eased),
                        )
                    if self._split_review_detail is not None:
                        self._split_review_detail.configure(fg=self._blend_hex("#111a24", "#b8c5d2", eased))
                    if progress < 1.0:
                        self._split_review_animation_job = self.window.after(16, text_step)
                    else:
                        self._split_review_animation_job = None

                if self._closed or self._split_review_window is None:
                    self._split_review_animation_job = None
                    return
                text_step()

            self._split_review_animation_job = self.window.after(45, begin_text)

        image_step()

    def _update_split_review_error(self, message: str) -> None:
        if self._split_review_badge is not None:
            self._split_review_badge.configure(text=self._text("UNCERTAIN", "NEJISTÉ"), bg="#f3c969")
        if self._split_review_detail is not None:
            self._split_review_detail.configure(text=message)
        if self._split_review_stage_var is not None:
            self._split_review_stage_var.set(self._text("Projection unavailable.", "Projekce není k dispozici."))
        if self._split_review_progress is not None:
            self._split_review_progress.pack_forget()
        if self._split_review_render is not None:
            self._split_review_render()

    def _update_split_review_unavailable(self, message: str) -> None:
        """Keep the source comparison visible when no trustworthy shoe exists."""
        if self._split_review_badge is not None:
            self._split_review_badge.configure(
                text=self._text("NOT AVAILABLE", "NENÍ K DISPOZICI"),
                bg="#69737d",
                fg="#f2f4f6",
            )
        if self._split_review_detail is not None:
            self._split_review_detail.configure(text=message, fg="#c5ccd3")
        if self._split_review_stage_var is not None:
            self._split_review_stage_var.set(self._text("Shoe detection failed.", "Detekce boty selhala."))
        if self._split_review_progress is not None:
            self._split_review_progress.pack_forget()
        if self._split_review_render is not None:
            self._split_review_render()

    def _close_split_review(self, _event=None) -> str:
        review = self._split_review_window
        self._split_review_window = None
        self._split_review_photos = []
        self._split_review_render = None
        self._split_review_progress = None
        self._split_review_stage_var = None
        self._split_review_badge = None
        self._split_review_detail = None
        self._split_review_reveal_image = None
        if self._split_review_animation_job is not None:
            try:
                self.window.after_cancel(self._split_review_animation_job)
            except tk.TclError:
                pass
            self._split_review_animation_job = None
        if review is not None:
            try:
                review.destroy()
            except tk.TclError:
                pass
        try:
            self.window.focus_force()
        except tk.TclError:
            pass
        if not self._closed and self._state in {"analysing_frame", "projection_unavailable"}:
            # A fullscreen failure review is transient. Returning from it must
            # reveal the projection menu so the operator can choose manual
            # setup or re-run the frame workflow instead of losing the window.
            self._state = "selecting_frame"
            self.workspace_page.grid_remove()
            self.selection_page.grid(row=1, column=0, sticky="nsew")
            if self._analysis_failure is not None:
                layer = str(self._analysis_failure.get("layer") or "shoe")
                label = {
                    "board": self._text("Set board manually", "Nastavit prkno ručně"),
                    "foul": self._text("Set foul line manually", "Nastavit odrazovou čáru ručně"),
                    "shoe": self._text("Set shoe outline manually", "Nastavit obrys boty ručně"),
                }.get(layer, self._text("Set up manually", "Nastavit ručně"))
                self.manual_setup_button.configure(text=label)
                self.manual_setup_button.pack(side="left", padx=(0, 6), before=self.confirm_frame_button)
            self._render_selection()
        elif not self._closed and self._state == "projection_workspace" and self._shoe_detection_failed():
            self.window.after_idle(lambda: self._render_result("overhead"))
        return "break"

    def _shoe_detection_failed(self) -> bool:
        return "shoe_detection_failed" in (
            self._analysis.diagnostics if self._analysis is not None else ()
        )

    def _projection_image(self, target: str) -> np.ndarray | None:
        """Return the calibrated top-down board view used by the operator."""
        return self._board_result
    def _render_result(self, target: str) -> None:
        canvas = self.board_canvas if target == "board" else self.overhead_canvas
        if not hasattr(canvas, "delete"): return
        canvas.delete("all")
        image = self._projection_image(target)
        if image is None:
            canvas.configure(cursor="arrow")
            canvas.create_text(
                max(20, canvas.winfo_width()/2),
                max(20, canvas.winfo_height()/2),
                text=self._text("Press Compute to create the top-down board view.", "Stisknutím Vypočítat vytvoříte pohled na prkno shora."),
                fill=self.palette["muted"],
                width=max(180, canvas.winfo_width()-30),
                justify="center",
            )
            canvas.create_window(
                max(20, canvas.winfo_width()/2),
                max(55, canvas.winfo_height()/2 + 42),
                window=self.board_compute_button if target == "board" else self.overhead_compute_button,
                anchor="center",
            )
            return
        if image.size == 0 or float(np.count_nonzero(image)) / float(image.size) < 0.02:
            canvas.configure(cursor="arrow")
            canvas.create_text(
                max(20, canvas.winfo_width() / 2),
                max(20, canvas.winfo_height() / 2),
                text=self._text("Projection image was empty. Re-analyse or correct the board points.", "Obraz projekce byl prázdný. Znovu analyzujte nebo opravte body prkna."),
                fill=self.palette["muted"],
                width=max(180, canvas.winfo_width() - 30),
            )
            return
        try:
            canvas.configure(cursor="hand2")
            available_width, available_height = max(200, canvas.winfo_width()-8), max(150, canvas.winfo_height()-8)
            image_height, image_width = image.shape[:2]
            scale = min(available_width/max(1, image_width), available_height/max(1, image_height))
            render_width, render_height = max(1, int(image_width*scale)), max(1, int(image_height*scale))
            photo = self._photo(image, (render_width, render_height))
            if target == "board": self._board_photo = photo
            else: self._overhead_photo = photo
            canvas.create_image(canvas.winfo_width()/2, canvas.winfo_height()/2, image=photo, anchor="center")
            if target == "overhead":
                left = (canvas.winfo_width()-render_width)/2; top = (canvas.winfo_height()-render_height)/2
                self._result_bounds = (left, top, left+render_width, top+render_height)
        except (ValueError, TypeError, cv2.error, tk.TclError) as exc:
            _LOGGER.exception("Could not display %s projection", target)
            canvas.configure(cursor="arrow")
            canvas.create_text(
                max(20, canvas.winfo_width() / 2),
                max(20, canvas.winfo_height() / 2),
                text=self._text(f"Could not display this projection: {exc}", f"Tuto projekci nelze zobrazit: {exc}"),
                fill="#ff8a96",
                width=max(180, canvas.winfo_width() - 30),
            )
            self.status_var.set(str(exc))

    def _result_hover(self, event) -> str:
        image = self._projection_image("overhead")
        if not self.mouse_zoom_var.get() or image is None:
            self._hide_result_magnifier(); return "break"
        left, top, right, bottom = self._result_bounds
        if not (left <= event.x <= right and top <= event.y <= bottom):
            self._hide_result_magnifier(); return "break"
        self._result_target = (
            (event.x-left)/max(1.0, right-left)*image.shape[1],
            (event.y-top)/max(1.0, bottom-top)*image.shape[0],
        )
        self._result_canvas_point = (float(event.x), float(event.y))
        if self._result_focus is None: self._result_focus = self._result_target
        if self._result_magnifier_job is None:
            self._result_magnifier_job = self.window.after(20, self._update_result_magnifier)
        return "break"
    def _update_result_magnifier(self) -> None:
        self._result_magnifier_job = None
        if self._closed or self._result_target is None or not self.mouse_zoom_var.get(): return
        target = np.asarray(self._result_target, np.float32)
        current = np.asarray(self._result_focus or self._result_target, np.float32)
        current += (target-current)*.52
        self._result_focus = (float(current[0]), float(current[1]))
        self._draw_result_magnifier()
        if float(np.linalg.norm(target-current)) > .3:
            self._result_magnifier_job = self.window.after(20, self._update_result_magnifier)

    @staticmethod
    def _draw_dashed_cv(image: np.ndarray, points: np.ndarray, colour: tuple[int, int, int], thickness: int = 2) -> None:
        if len(points) < 2: return
        closed = np.vstack((points, points[0]))
        for start, end in zip(closed[:-1], closed[1:]):
            delta = end.astype(np.float32)-start.astype(np.float32); length = max(1., float(np.linalg.norm(delta)))
            direction = delta/length
            for position in np.arange(0., length, 15.):
                a = np.rint(start+direction*position).astype(int); b = np.rint(start+direction*min(length, position+9.)).astype(int)
                cv2.line(image, tuple(a), tuple(b), colour, thickness, cv2.LINE_AA)

    def _draw_result_magnifier(self) -> None:
        source = self._projection_image("overhead")
        if source is None or self._result_focus is None:
            return
        source = source.copy(); height, width = source.shape[:2]
        zoom_w, zoom_h = 340, 230
        crop_w = max(30, min(width, int(round(zoom_w/self._magnifier_factor))))
        crop_h = max(22, min(height, int(round(zoom_h/self._magnifier_factor))))
        fx, fy = self._result_focus
        x0 = max(0, min(width-crop_w, int(round(fx-crop_w/2))))
        y0 = max(0, min(height-crop_h, int(round(fy-crop_h/2))))
        crop = source[y0:y0+crop_h, x0:x0+crop_w]
        if crop.size == 0:
            return
        zoom = cv2.resize(crop, (zoom_w, zoom_h), interpolation=cv2.INTER_CUBIC)
        sx, sy = zoom_w/max(1, crop_w), zoom_h/max(1, crop_h)
        cross_x, cross_y = int(round((fx-x0)*sx)), int(round((fy-y0)*sy))
        cv2.line(zoom, (cross_x-9,cross_y), (cross_x+9,cross_y), (235,241,247), 1, cv2.LINE_AA)
        cv2.line(zoom, (cross_x,cross_y-9), (cross_x,cross_y+9), (235,241,247), 1, cv2.LINE_AA)
        cv2.rectangle(zoom, (0,0), (zoom_w-1,zoom_h-1), (205,220,235), 1)
        self._zoom_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(zoom, cv2.COLOR_BGR2RGB)))
        canvas = self.overhead_canvas; canvas.delete("magnifier")
        event_x, event_y = self._result_canvas_point
        px = min(max(zoom_w/2+5,event_x+zoom_w/2+18), max(zoom_w/2+5,canvas.winfo_width()-zoom_w/2-5))
        py = min(max(zoom_h/2+5,event_y+zoom_h/2+18), max(zoom_h/2+5,canvas.winfo_height()-zoom_h/2-5))
        canvas.create_image(px, py, image=self._zoom_photo, anchor="center", tags="magnifier")
    def _hide_result_magnifier(self, _event=None) -> None:
        self._result_target = None
        if self._result_magnifier_job is not None:
            try: self.window.after_cancel(self._result_magnifier_job)
            except tk.TclError: pass
            self._result_magnifier_job = None
        if hasattr(self, "overhead_canvas"): self.overhead_canvas.delete("magnifier")

    def _result_magnifier_wheel(self, event) -> str:
        if not self.mouse_zoom_var.get(): return "break"
        direction = 1 if getattr(event,"num",None)==4 or getattr(event,"delta",0)>0 else -1
        self._magnifier_factor = max(1.5,min(8.0,self._magnifier_factor*(1.16 if direction>0 else 1/1.16)))
        return self._result_hover(event)

    def _open_fullscreen(self, target: str, _event=None) -> str:
        image = self._projection_image(target)
        if image is None or self._fullscreen_window is not None:
            return "break"
        self._fullscreen_image = image.copy()
        fullscreen = tk.Toplevel(self.window)
        self._fullscreen_window = fullscreen
        fullscreen.configure(bg="#000000")
        fullscreen.title(self._text("Top-down projection", "Projekce shora"))
        fullscreen.protocol("WM_DELETE_WINDOW", self._exit_fullscreen)
        fullscreen.bind("<KeyPress>", self._exit_fullscreen)
        fullscreen.bind("<Escape>", self._exit_fullscreen)
        fullscreen.bind("<MouseWheel>", self._fullscreen_wheel)
        fullscreen.bind("<Button-4>", self._fullscreen_wheel)
        fullscreen.bind("<Button-5>", self._fullscreen_wheel)
        fullscreen.attributes("-fullscreen", True)
        canvas = tk.Canvas(fullscreen, bg="#000000", highlightthickness=0, cursor="crosshair")
        self._fullscreen_canvas = canvas
        canvas.pack(fill="both", expand=True)
        bind_resize_only(canvas, lambda _event: self._fit_fullscreen_image())
        canvas.bind("<ButtonPress-1>", self._fullscreen_pan_start)
        canvas.bind("<B1-Motion>", self._fullscreen_pan)
        canvas.bind("<ButtonRelease-1>", self._fullscreen_pan_end)
        canvas.bind("<Double-Button-1>", self._fullscreen_reset)
        self._fullscreen_scale = 1.0
        self._fullscreen_offset = (0.0, 0.0)
        fullscreen.after_idle(lambda: (fullscreen.focus_force(), self._fit_fullscreen_image()))
        return "break"

    def _fit_fullscreen_image(self) -> None:
        if self._fullscreen_window is None or self._fullscreen_canvas is None or self._fullscreen_image is None:
            return
        canvas = self._fullscreen_canvas
        width, height = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        image_height, image_width = self._fullscreen_image.shape[:2]
        self._fullscreen_scale = min(width / max(1, image_width), height / max(1, image_height))
        self._fullscreen_fit_scale = self._fullscreen_scale
        shown_width, shown_height = image_width * self._fullscreen_scale, image_height * self._fullscreen_scale
        self._fullscreen_offset = ((width - shown_width) / 2.0, (height - shown_height) / 2.0)
        self._render_fullscreen_image()

    def _render_fullscreen_image(self) -> None:
        if self._fullscreen_canvas is None or self._fullscreen_image is None:
            return
        canvas = self._fullscreen_canvas
        canvas.delete("all")
        image_height, image_width = self._fullscreen_image.shape[:2]
        shown_width = max(1, int(round(image_width * self._fullscreen_scale)))
        shown_height = max(1, int(round(image_height * self._fullscreen_scale)))
        shown = cv2.resize(self._fullscreen_image, (shown_width, shown_height), interpolation=cv2.INTER_AREA if self._fullscreen_scale < 1 else cv2.INTER_LINEAR)
        self._fullscreen_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)))
        self._fullscreen_canvas.create_image(self._fullscreen_offset[0], self._fullscreen_offset[1], image=self._fullscreen_photo, anchor="nw")
        self._fullscreen_canvas.create_text(18, 16, text=self._text("Press any key to exit  •  Scroll to zoom", "Stisknutím klávesy ukončíte  •  Kolečkem přiblížíte"), fill="#e7edf5", anchor="nw")
        summary = self._measurement_summary()
        if summary:
            canvas_width = max(300, self._fullscreen_canvas.winfo_width())
            canvas_height = max(180, self._fullscreen_canvas.winfo_height())
            self._fullscreen_canvas.create_rectangle(14, canvas_height - 58, min(canvas_width - 14, 390), canvas_height - 14, fill="#111722", outline="#70d6a5", width=1)
            self._fullscreen_canvas.create_text(26, canvas_height - 36, text=summary, fill="#f2f6fa", anchor="w", font=("Segoe UI", 13, "bold"))

    def _measurement_summary(self) -> str:
        automatic = self._automatic_verdict_display()
        if automatic is not None:
            return automatic[0]
        if self._overhead_result is not None:
            return projection_verdict_text(self._overhead_result.verdict_status)
        if self.calibration is None or len(self._foot_points) < 3 or self._source_frame_size[0] <= 1:
            return ""
        try:
            measurement = measure_projected_foot(self._foot_points, self.calibration, self._source_frame_size, confidence=self._foot_confidence or .65)
            return projection_verdict_text(measurement.status)
        except (ValueError, cv2.error):
            return ""

    def _fullscreen_wheel(self, event) -> str:
        if self._fullscreen_canvas is None or self._fullscreen_image is None:
            return "break"
        if getattr(event, "num", None) == 4:
            direction = 1
        elif getattr(event, "num", None) == 5:
            direction = -1
        else:
            direction = 1 if getattr(event, "delta", 0) > 0 else -1
        factor = 1.16 if direction > 0 else 1 / 1.16
        old_scale = self._fullscreen_scale
        new_scale = max(self._fullscreen_fit_scale, min(self._fullscreen_fit_scale * 8.0, old_scale * factor))
        if abs(new_scale - old_scale) < 1e-6:
            return "break"
        pointer_x, pointer_y = float(event.x), float(event.y)
        image_x = (pointer_x - self._fullscreen_offset[0]) / old_scale
        image_y = (pointer_y - self._fullscreen_offset[1]) / old_scale
        self._fullscreen_scale = new_scale
        self._fullscreen_offset = (pointer_x - image_x * new_scale, pointer_y - image_y * new_scale)
        self._render_fullscreen_image()
        return "break"

    def _fullscreen_pan_start(self, event) -> str:
        self._fullscreen_drag_start = (float(event.x), float(event.y)); return "break"

    def _fullscreen_pan(self, event) -> str:
        if self._fullscreen_drag_start is None: return "break"
        x, y = self._fullscreen_drag_start
        self._fullscreen_offset = (self._fullscreen_offset[0]+event.x-x, self._fullscreen_offset[1]+event.y-y)
        self._fullscreen_drag_start = (float(event.x), float(event.y)); self._render_fullscreen_image(); return "break"

    def _fullscreen_pan_end(self, _event=None) -> str:
        self._fullscreen_drag_start = None; return "break"

    def _fullscreen_reset(self, _event=None) -> str:
        self._fit_fullscreen_image(); return "break"

    def _exit_fullscreen(self, _event=None) -> str:
        fullscreen = self._fullscreen_window
        self._fullscreen_window = None
        self._fullscreen_canvas = None
        self._fullscreen_image = None
        self._fullscreen_photo = None
        if fullscreen is not None:
            try:
                fullscreen.grab_release()
                fullscreen.destroy()
            except tk.TclError:
                pass
        try:
            self.window.focus_force()
        except tk.TclError:
            pass
        return "break"

    def _flip_legal_side(self) -> None:
        if self.calibration is None: return
        self.calibration = replace(self.calibration, legal_side_flipped=not self.calibration.legal_side_flipped)
        self.on_calibration_saved(self.calibration); self._invalidate_results()

    def _open_camera_profile_wizard(self) -> None:
        dialog = tk.Toplevel(self.window); center_popup(dialog); dialog.title(self._text("Advanced camera profile", "Pokročilý profil kamery")); dialog.transient(self.window)
        frame = ttk.Frame(dialog, style="Panel.TFrame", padding=16); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=self._text("Optional checkerboard camera profile", "Volitelný profil kamery se šachovnicí"), style="Title.TLabel").pack(anchor="w")
        result_var = tk.StringVar(value="")
        ttk.Label(frame, text=self._text("Use at least three sharp checkerboard views. This improves correction for close wide-angle cameras.", "Použijte alespoň tři ostré pohledy na šachovnici. Zlepší to korekci blízkých širokoúhlých kamer."), style="Muted.TLabel", wraplength=500).pack(anchor="w", pady=(6, 10))
        ttk.Label(frame, textvariable=result_var, style="Status.TLabel").pack(anchor="w")
        ttk.Checkbutton(
            frame,
            text=self._text("Show detection diagnostics on the source frame", "Zobrazit diagnostiku detekce ve zdrojovém snímku"),
            variable=self.debug_overlay_var,
            command=self._toggle_debug_overlay,
        ).pack(anchor="w", pady=(8, 0))
        buttons = ttk.Frame(frame, style="Panel.TFrame"); buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text=self._text("Open checkerboard", "Otevřít šachovnici"), command=lambda: os.startfile(str(checkerboard_asset_path()))).pack(side="left")
        def analyse() -> None:
            profile_frames = [candidate.frame_bgr for candidate in self.candidates] + list(self.reference_frames)
            profile = estimate_camera_profile(profile_frames)
            if profile is None: result_var.set(self._text("Need three distinct checkerboard views.", "Jsou potřeba tři odlišné pohledy na šachovnici.")); return
            if self.calibration:
                self.calibration = replace(self.calibration, camera_profile=profile); self.on_calibration_saved(self.calibration); self._invalidate_results()
            result_var.set(self._text("Camera profile saved.", "Profil kamery byl uložen."))
        ttk.Button(buttons, text=self._text("Analyse", "Analyzovat"), command=analyse).pack(side="left", padx=6)
        ttk.Button(buttons, text=self._text("Close", "Zavřít"), command=dialog.destroy).pack(side="right")

    def _cancel_work(self) -> None:
        if self._cancel is not None: self._cancel.set()
        self._cancel = None

    def close(self) -> None:
        if self._closed: return
        self._closed = True; self._cancel_work(); self._generation += 1
        self._hide_source_magnifier(); self._hide_result_magnifier()
        self._close_split_review()
        self._exit_fullscreen()
        if self._analysis_dialog: self._analysis_dialog.close(); self._analysis_dialog = None
        try: self.window.destroy()
        finally: self.on_close()
