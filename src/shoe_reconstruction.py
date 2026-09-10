from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time
from threading import Event
from typing import Callable, Sequence

import cv2
import numpy as np

from .portable_paths import bundled_resource


CHECKERBOARD_INNER_CORNERS = (8, 5)
CHECKERBOARD_SQUARE_MM = 25.0


class ReconstructionTimedOut(RuntimeError):
    pass


class ReconstructionCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ShoeModelParameters:
    position_cm: tuple[float, float]
    rotation_deg: float
    length_cm: float
    width_cm: float
    heel_roundness: float
    toe_roundness: float
    sole_thickness_cm: float
    upper_height_cm: float


@dataclass(frozen=True, slots=True)
class MeshGeometry:
    vertices: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class ReconstructionResult:
    mesh_geometry: MeshGeometry
    sole_footprint: tuple[tuple[float, float], ...]
    camera_pose: dict[str, object]
    fit_confidence: float
    diagnostics: tuple[str, ...]
    overhead_image: np.ndarray
    fit_variation_cm: float
    clean_overhead_image: np.ndarray | None = None
    # Optional evidence layers for diagnostics and future contact refinement.
    # They are kept out of the persisted calibration and never replace the
    # original source frame.
    observed_mask: np.ndarray | None = None
    estimated_mask: np.ndarray | None = None
    contact_mask: np.ndarray | None = None
    verdict_status: str = "review"


def checkerboard_asset_path() -> Path:
    return bundled_resource("assets/camera-checkerboard.svg")


def estimate_camera_profile(
    frames: Sequence[np.ndarray],
    image_size: tuple[int, int] | None = None,
) -> dict[str, object] | None:
    """Create an optional local lens profile from at least three checkerboard views."""
    object_points: list[np.ndarray] = []
    image_points: list[np.ndarray] = []
    template = np.zeros((CHECKERBOARD_INNER_CORNERS[0] * CHECKERBOARD_INNER_CORNERS[1], 3), np.float32)
    template[:, :2] = np.mgrid[0:CHECKERBOARD_INNER_CORNERS[0], 0:CHECKERBOARD_INNER_CORNERS[1]].T.reshape(-1, 2)
    template *= CHECKERBOARD_SQUARE_MM / 10.0
    size = image_size
    signatures: list[np.ndarray] = []
    for frame in frames:
        if frame is None or frame.ndim != 3:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        size = (gray.shape[1], gray.shape[0])
        found, corners = cv2.findChessboardCorners(gray, CHECKERBOARD_INNER_CORNERS)
        if not found:
            continue
        refined = cv2.cornerSubPix(gray, corners, (9, 9), (-1, -1), (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_MAX_ITER, 30, .01))
        signature = refined.reshape(-1, 2).mean(axis=0)
        if any(float(np.linalg.norm(signature - previous)) < 12.0 for previous in signatures):
            continue
        signatures.append(signature)
        object_points.append(template.copy())
        image_points.append(refined)
    if len(image_points) < 3 or size is None:
        return None
    error, matrix, distortion, _rvecs, _tvecs = cv2.calibrateCamera(object_points, image_points, size, None, None)
    if not np.isfinite(error) or error > 3.0:
        return None
    return {
        "image_width": int(size[0]),
        "image_height": int(size[1]),
        "camera_matrix": matrix.tolist(),
        "distortion": distortion.reshape(-1).tolist(),
        "rms_error_px": float(error),
        "checkerboard_inner_corners": list(CHECKERBOARD_INNER_CORNERS),
        "square_mm": CHECKERBOARD_SQUARE_MM,
    }


def _check(deadline: float, cancel: Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ReconstructionCancelled("Reconstruction was cancelled")
    if time.monotonic() >= deadline:
        raise ReconstructionTimedOut("Reconstruction exceeded five seconds")


def _shoe_outline(params: ShoeModelParameters, samples: int = 32) -> np.ndarray:
    x_values = np.linspace(-.5, .5, max(12, samples // 2), dtype=np.float32)
    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for x in x_values:
        # A fourth-power superellipse gives a realistic flat sole side while
        # retaining rounded heel/toe ends.
        base = max(0.0, 1.0 - (2.0 * float(x)) ** 4) ** .25
        blend = float(x + .5)
        end_shape = params.heel_roundness * (1.0 - blend) + params.toe_roundness * blend
        half_width = params.width_cm * .5 * base * (.72 + .28 * end_shape)
        upper.append((float(x) * params.length_cm, half_width))
        lower.append((float(x) * params.length_cm, -half_width))
    local = np.asarray(upper + lower[::-1], dtype=np.float32)
    angle = math.radians(params.rotation_deg)
    rotation = np.asarray([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]], dtype=np.float32)
    return local @ rotation.T + np.asarray(params.position_cm, dtype=np.float32)


def _initial_parameters(points_cm: np.ndarray) -> ShoeModelParameters:
    rect = cv2.minAreaRect(points_cm.astype(np.float32))
    (cx, cy), (first, second), angle = rect
    if first < second:
        first, second = second, first
        angle += 90.0
    length = min(38.0, max(14.0, float(first)))
    auto_width = min(13.0, max(6.0, max(float(second), length * .34)))
    return ShoeModelParameters((float(cx), float(cy)), float(angle), length, auto_width, .78, .95, 1.8, 6.5)


def _fit_error(points_cm: np.ndarray, params: ShoeModelParameters) -> float:
    outline = _shoe_outline(params)
    contour = outline.reshape((-1, 1, 2)).astype(np.float32)
    distances = [abs(float(cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), True))) for point in points_cm]
    coverage = sum(cv2.pointPolygonTest(contour, (float(point[0]), float(point[1])), False) >= 0 for point in points_cm) / max(1, len(points_cm))
    return float(np.mean(distances)) + (1.0 - coverage) * 2.5


def _fit_deterministic(
    points_cm: np.ndarray,
    deadline: float,
    cancel: Event | None,
    dimension_hint: tuple[float, float] | None = None,
) -> tuple[ShoeModelParameters, float]:
    best = _initial_parameters(points_cm)
    if dimension_hint is not None:
        best = ShoeModelParameters(
            best.position_cm, best.rotation_deg,
            min(38.0, max(14.0, dimension_hint[0])),
            min(13.0, max(6.0, max(dimension_hint[1], dimension_hint[0] * .30))),
            best.heel_roundness, best.toe_roundness, best.sole_thickness_cm, best.upper_height_cm,
        )
    best_error = _fit_error(points_cm, best)
    # Coarse and fine bounded grids. Width follows length unless observations
    # require a larger value, making it automatic rather than operator-entered.
    for angle_step, length_step, position_step in ((9.0, 2.0, 1.2), (2.0, .6, .35)):
        origin = best
        for angle_delta in (-angle_step, 0.0, angle_step):
            for length_delta in (-length_step, 0.0, length_step):
                for dx in (-position_step, 0.0, position_step):
                    for dy in (-position_step, 0.0, position_step):
                        _check(deadline, cancel)
                        length = min(38.0, max(14.0, origin.length_cm + length_delta))
                        width = min(13.0, max(6.0, origin.width_cm + length_delta * .18))
                        for heel, toe in ((.70, .88), (.78, .95), (.86, 1.0)):
                            candidate = ShoeModelParameters(
                                (origin.position_cm[0] + dx, origin.position_cm[1] + dy),
                                origin.rotation_deg + angle_delta,
                                length, width, heel, toe, 1.8, 6.5,
                            )
                            error = _fit_error(points_cm, candidate)
                            if error < best_error:
                                best, best_error = candidate, error
    return best, best_error


def _normalise_outline_for_fit(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Scale apparent geometry to a stable model size without validating real length."""
    values = np.asarray(points, dtype=np.float32)
    if values.shape[0] < 3 or not np.isfinite(values).all():
        raise ValueError("A finite sole contact outline is required")
    rect = cv2.minAreaRect(values)
    apparent_long_side = max(float(rect[1][0]), float(rect[1][1]))
    if apparent_long_side <= 1e-5:
        raise ValueError("The sole contact outline has no usable area")
    centre = np.asarray(rect[0], dtype=np.float32)
    scale = max(.03, min(30.0, 26.0 / apparent_long_side))
    return centre + (values - centre) * scale, scale


def _sample_closed_outline(points: np.ndarray, count: int = 48) -> np.ndarray:
    values = np.asarray(points, dtype=np.float32).reshape((-1, 2))
    if len(values) < 3:
        return values
    closed = np.vstack((values, values[0]))
    lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    perimeter = float(lengths.sum())
    if perimeter <= 1e-5:
        return values
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    targets = np.linspace(0.0, perimeter, max(8, count), endpoint=False)
    result = []
    for target in targets:
        segment = min(len(lengths) - 1, int(np.searchsorted(cumulative, target, side="right") - 1))
        fraction = (target - cumulative[segment]) / max(1e-6, float(lengths[segment]))
        result.append(closed[segment] + (closed[segment + 1] - closed[segment]) * fraction)
    return np.asarray(result, dtype=np.float32)


def _track_outline_between_frames(
    source_frame: np.ndarray,
    target_frame: np.ndarray,
    outline_px: Sequence[Sequence[float]],
) -> np.ndarray | None:
    """Propagate a measured outline with sparse optical flow.

    This is only a neighbour-frame consistency observation. The selected
    frame's measured outline remains authoritative.
    """
    if source_frame is None or target_frame is None or source_frame.shape != target_frame.shape:
        return None
    scale = min(1.0, 720.0 / max(1, source_frame.shape[1]))
    size = None if scale >= 1.0 else (max(8, int(source_frame.shape[1] * scale)), max(8, int(source_frame.shape[0] * scale)))
    source_gray = cv2.cvtColor(source_frame, cv2.COLOR_BGR2GRAY)
    target_gray = cv2.cvtColor(target_frame, cv2.COLOR_BGR2GRAY)
    if size is not None:
        source_gray = cv2.resize(source_gray, size, interpolation=cv2.INTER_AREA)
        target_gray = cv2.resize(target_gray, size, interpolation=cv2.INTER_AREA)
    samples = _sample_closed_outline(np.asarray(outline_px, np.float32), 48) * scale
    tracked, status, errors = cv2.calcOpticalFlowPyrLK(
        source_gray,
        target_gray,
        samples.reshape((-1, 1, 2)),
        None,
        winSize=(21, 21),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
    )
    if tracked is None or status is None:
        return None
    good = status.reshape(-1) > 0
    if int(np.count_nonzero(good)) < max(6, int(len(samples) * .60)):
        return None
    if errors is not None and float(np.median(errors.reshape(-1)[good])) > 24.0:
        return None
    affine, _inliers = cv2.estimateAffinePartial2D(
        samples[good], tracked.reshape((-1, 2))[good], method=cv2.RANSAC, ransacReprojThreshold=3.5,
    )
    if affine is None:
        return None
    original = np.asarray(outline_px, np.float32).reshape((-1, 1, 2)) * scale
    return cv2.transform(original, affine).reshape((-1, 2)) / max(scale, 1e-6)


def _mesh(params: ShoeModelParameters) -> MeshGeometry:
    sole = _shoe_outline(params, 28)
    centre = np.asarray(params.position_cm, dtype=np.float32)
    upper = centre + (sole - centre) * .76
    vertices = [(float(x), float(y), 0.0) for x, y in sole]
    vertices += [(float(x), float(y), params.sole_thickness_cm) for x, y in sole]
    vertices += [(float(x), float(y), params.sole_thickness_cm + params.upper_height_cm) for x, y in upper]
    count = len(sole)
    faces: list[tuple[int, ...]] = [tuple(range(count)), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
        faces.append((count + index, count + nxt, count * 2 + nxt, count * 2 + index))
    faces.append(tuple(range(count * 2, count * 3)))
    return MeshGeometry(tuple(vertices), tuple(faces))


def _render_overhead(
    frame: np.ndarray,
    calibration,
    frame_size: tuple[int, int],
    params: ShoeModelParameters,
    footprint_normalized: np.ndarray,
    judging_status: str,
    show_overlays: bool = True,
    observed_footprint_normalized: np.ndarray | None = None,
    base_image: np.ndarray | None = None,
) -> np.ndarray:
    from .top_view_projection import (
        compute_physical_pad_homography,
        corrected_projection_calibration,
        project_points_to_pad,
        undistort_frame_for_projection,
    )
    source_calibration = calibration
    calibration = corrected_projection_calibration(source_calibration, frame_size)
    foul_source = np.asarray(calibration.foul_line, dtype=np.float32) * np.asarray(frame_size, dtype=np.float32)
    foul = project_points_to_pad(foul_source, calibration.board_corners, frame_size)
    horizontal = abs(float(foul[1, 0] - foul[0, 0])) >= abs(float(foul[1, 1] - foul[0, 1]))
    length_cm = calibration.pad_length_cm or 120.1
    width_cm = calibration.pad_width_cm or 34.0
    if base_image is None:
        frame = undistort_frame_for_projection(frame, source_calibration)
        homography = compute_physical_pad_homography(calibration.board_corners, calibration.foul_line, frame_size, (900, 255))
        raw = cv2.warpPerspective(frame, homography, (900, 255))
        valid = cv2.warpPerspective(
            np.full(frame.shape[:2], 255, dtype=np.uint8),
            homography,
            (900, 255),
            flags=cv2.INTER_NEAREST,
        )
        valid_fraction = float(np.count_nonzero(valid)) / float(max(1, valid.size))
        visible_fraction = float(np.count_nonzero(raw)) / float(max(1, raw.size))
        if raw.size and (valid_fraction < 0.45 or visible_fraction < 0.02):
            source = np.asarray(calibration.board_corners, np.float32) * np.asarray(frame_size, np.float32)
            x0, y0 = np.floor(source.min(axis=0)).astype(int)
            x1, y1 = np.ceil(source.max(axis=0)).astype(int)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(frame.shape[1], x1), min(frame.shape[0], y1)
            crop = frame[y0:y1, x0:x1]
            if crop.size:
                raw = cv2.resize(crop, (900, 255), interpolation=cv2.INTER_AREA)
    else:
        raw = np.asarray(base_image, dtype=np.uint8).copy()
    # Keep the raster itself clean and tightly framed. Titles, verdict and
    # legend belong to the surrounding UI where they cannot overlap evidence.
    canvas = raw.copy()
    def metric_to_canvas(points: np.ndarray) -> np.ndarray:
        result = np.empty_like(points, dtype=np.float32)
        result[:, 0] = points[:, 0] / max(.1, length_cm) * 899
        result[:, 1] = points[:, 1] / max(.1, width_cm) * 254
        return np.rint(result).astype(np.int32)

    def dashed_outline(points: np.ndarray, colour: tuple[int, int, int], thickness: int = 2) -> None:
        if len(points) < 2:
            return
        closed = np.vstack((points, points[0]))
        for start, end in zip(closed[:-1], closed[1:]):
            delta = end.astype(np.float32) - start.astype(np.float32)
            length = max(1.0, float(np.linalg.norm(delta)))
            direction = delta / length
            position = 0.0
            while position < length:
                segment_end = min(length, position + 9.0)
                a = np.rint(start + direction * position).astype(int)
                b = np.rint(start + direction * segment_end).astype(int)
                cv2.line(canvas, tuple(a), tuple(b), colour, thickness, cv2.LINE_AA)
                position += 15.0
    sole_cm = _shoe_outline(params)
    sole_px = metric_to_canvas(sole_cm)
    if show_overlays:
        overlay = canvas.copy()
        cv2.fillPoly(overlay, [sole_px], (40, 190, 245))
        cv2.addWeighted(overlay, .16, canvas, .84, 0, canvas)
        dashed_outline(sole_px, (35, 235, 255), 2)
    upper = np.asarray(params.position_cm, dtype=np.float32) + (sole_cm - np.asarray(params.position_cm, dtype=np.float32)) * .76
    upper_px = metric_to_canvas(upper)
    if show_overlays:
        hidden = canvas.copy()
        cv2.fillPoly(hidden, [upper_px], (135, 145, 155))
        cv2.addWeighted(hidden, .28, canvas, .72, 0, canvas)
        dashed_outline(upper_px, (195, 202, 208), 2)
        if observed_footprint_normalized is not None and len(observed_footprint_normalized) >= 3:
            observed_metric = np.asarray(observed_footprint_normalized, np.float32) * np.asarray([length_cm, width_cm], np.float32)
            observed_px = metric_to_canvas(observed_metric)
            cv2.polylines(canvas, [observed_px], True, (80, 220, 170), 3, cv2.LINE_AA)
    foul_metric = footprint_normalized[:0]
    if horizontal:
        foul_metric = foul * np.asarray([length_cm, width_cm], np.float32)
    else:
        foul_metric = foul[:, [1, 0]] * np.asarray([length_cm, width_cm], np.float32)
    foul_px = metric_to_canvas(foul_metric)
    if show_overlays:
        cv2.line(canvas, tuple(foul_px[0]), tuple(foul_px[1]), (75, 75, 245), 3, cv2.LINE_AA)
    return canvas


def reconstruct_shoe_overhead(
    selected_frame: np.ndarray,
    selected_outline_px: Sequence[Sequence[float]],
    observations: Sequence[tuple[int, np.ndarray]],
    reference_frames: Sequence[np.ndarray],
    calibration,
    *,
    time_limit_seconds: float = 5.0,
    cancel: Event | None = None,
    progress: Callable[[str, int], None] | None = None,
) -> ReconstructionResult:
    """Fit and render a bounded local shoe model; never returns an invented fit."""
    from .top_view_projection import estimate_foot_polygon, project_points_to_board_cm, project_points_to_pad

    started = time.perf_counter()
    deadline = time.monotonic() + max(0.0, float(time_limit_seconds))
    report = progress or (lambda _stage, _value: None)
    _check(deadline, cancel)
    report("preparing_frames", 10)
    if selected_frame is None or len(selected_outline_px) < 3:
        raise ValueError("A measured sole outline is required")
    frame_size = (selected_frame.shape[1], selected_frame.shape[0])
    accepted: list[np.ndarray] = [np.asarray(selected_outline_px, dtype=np.float32)]
    selected_cm = project_points_to_board_cm(selected_outline_px, calibration, frame_size)
    selected_rect = cv2.minAreaRect(selected_cm.astype(np.float32))[1]
    selected_dims = (max(selected_rect), max(.1, min(selected_rect)))
    fit_points, fit_scale = _normalise_outline_for_fit(selected_cm)
    rejected = {"blurred": 0, "duplicate": 0, "shadow": 0, "tracking": 0, "inconsistent": 0}
    selected_gray_small = cv2.resize(cv2.cvtColor(selected_frame, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
    seen: list[np.ndarray] = [selected_gray_small]
    tracked_observations = 0
    full_refinements = 0
    resized_reference_cache: dict[tuple[int, int], list[np.ndarray]] = {}
    sharpness_values = [float(cv2.Laplacian(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()) for _index, frame in observations if frame is not None]
    blur_floor = max(8.0, (float(np.median(sharpness_values)) * .25) if sharpness_values else 8.0)
    report("isolating_shoe", 30)
    for _index, frame in observations[:7]:
        _check(deadline, cancel)
        if frame is None or frame.shape != selected_frame.shape:
            rejected["inconsistent"] += 1
            continue
        gray_small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
        if float(cv2.Laplacian(gray_small, cv2.CV_64F).var()) < blur_floor * .05:
            rejected["blurred"] += 1
            continue
        if any(float(np.mean(cv2.absdiff(gray_small, prior))) < 1.2 for prior in seen):
            rejected["duplicate"] += 1
            continue
        seen.append(gray_small)
        outline = _track_outline_between_frames(selected_frame, frame, selected_outline_px)
        if outline is not None:
            tracked_observations += 1
        elif full_refinements < 2:
            # Full segmentation is a bounded fallback, not repeated for every
            # neighbour. Most consistent frames use inexpensive mask tracking.
            full_refinements += 1
            analysis_scale = min(1.0, 720.0 / max(1, frame.shape[1]))
            if analysis_scale < 1.0:
                analysis_frame = cv2.resize(frame, None, fx=analysis_scale, fy=analysis_scale, interpolation=cv2.INTER_AREA)
                cache_key = (analysis_frame.shape[1], analysis_frame.shape[0])
                analysis_references = resized_reference_cache.get(cache_key)
                if analysis_references is None:
                    analysis_references = [
                        cv2.resize(reference, cache_key, interpolation=cv2.INTER_AREA)
                        for reference in reference_frames if reference is not None and reference.shape == frame.shape
                    ]
                    resized_reference_cache[cache_key] = analysis_references
            else:
                analysis_frame = frame
                analysis_references = list(reference_frames)
            estimate = estimate_foot_polygon(analysis_frame, analysis_references, (0, 0, 1, 1), calibration.board_corners, calibration.foul_line)
            if estimate is None or estimate.confidence < .28:
                rejected["shadow"] += 1
                continue
            outline = np.asarray(estimate.polygon_px, dtype=np.float32) / analysis_scale
        else:
            rejected["tracking"] += 1
            continue
        observed_cm = project_points_to_board_cm(outline, calibration, frame_size)
        observed_rect = cv2.minAreaRect(observed_cm.astype(np.float32))[1]
        observed_dims = (max(observed_rect), max(.1, min(observed_rect)))
        if not (.55 <= observed_dims[0] / max(.1, selected_dims[0]) <= 1.65 and .40 <= observed_dims[1] / max(.1, selected_dims[1]) <= 2.0):
            rejected["inconsistent"] += 1
            continue
        accepted.append(outline)
    _check(deadline, cancel)
    report("fitting_model", 55)
    dimensions = []
    for outline in accepted:
        rect_size = cv2.minAreaRect(project_points_to_board_cm(outline, calibration, frame_size).astype(np.float32))[1]
        dimensions.append((max(rect_size), min(rect_size)))
    dimension_hint = tuple(float(np.median([value[index] for value in dimensions])) * fit_scale for index in (0, 1))
    fitted, error = _fit_deterministic(fit_points, deadline, cancel, dimension_hint)
    model_outline = _shoe_outline(fitted)
    scale = max(1.0, fitted.width_cm)
    fit_confidence = max(0.0, min(1.0, 1.0 - error / (scale * .65)))
    distances: list[float] = []
    from .top_view_projection import measure_projected_foot
    selected_measurement = measure_projected_foot(selected_outline_px, calibration, frame_size, confidence=.65)
    for outline in accepted:
        measurement = measure_projected_foot(outline, calibration, frame_size, confidence=.65)
        distances.append(measurement.signed_clearance_cm)
    fit_variation = float(np.std(distances)) if len(distances) > 1 else 0.0
    length_cm = calibration.pad_length_cm or 120.1
    width_cm = calibration.pad_width_cm or 34.0
    # Convert physical board coordinates directly back to normalized board axes.
    normalized = model_outline / np.asarray([length_cm, width_cm], dtype=np.float32)
    foul_source = np.asarray(calibration.foul_line, np.float32) * np.asarray(frame_size, np.float32)
    foul = project_points_to_pad(foul_source, calibration.board_corners, frame_size)
    if abs(float(foul[1, 0] - foul[0, 0])) < abs(float(foul[1, 1] - foul[0, 1])):
        normalized = normalized[:, [1, 0]]
    verdict_status = selected_measurement.status if fit_confidence >= .38 else "review"
    observed_norm = project_points_to_board_cm(selected_outline_px, calibration, frame_size)
    observed_norm = observed_norm / np.asarray([length_cm, width_cm], dtype=np.float32)
    if abs(float(foul[1, 0] - foul[0, 0])) < abs(float(foul[1, 1] - foul[0, 1])):
        observed_norm = observed_norm[:, [1, 0]]
    _check(deadline, cancel)
    report("rendering", 88)
    # Rectify the camera frame once. The overlay image is drawn on a copy of
    # that clean raster instead of repeating undistortion and two perspective
    # warps for the same projection.
    clean_image = _render_overhead(selected_frame, calibration, frame_size, fitted, normalized, verdict_status, False, observed_norm)
    image = _render_overhead(
        selected_frame, calibration, frame_size, fitted, normalized, verdict_status,
        True, observed_norm, base_image=clean_image,
    )
    _check(deadline, cancel)
    if abs(float(foul[1, 0] - foul[0, 0])) >= abs(float(foul[1, 1] - foul[0, 1])):
        destination = np.asarray([[0, 0], [length_cm, 0], [length_cm, width_cm], [0, width_cm]], np.float32)
    else:
        destination = np.asarray([[0, 0], [0, width_cm], [length_cm, width_cm], [length_cm, 0]], np.float32)
    homography = cv2.getPerspectiveTransform(
        np.asarray(calibration.board_corners, np.float32) * np.asarray(frame_size, np.float32), destination,
    )
    def raster(points: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
        mask = np.zeros((255, 900), dtype=np.uint8)
        values = np.asarray(points, dtype=np.float32)
        if values.shape[0] >= 3:
            px = np.rint(values * np.asarray([899.0, 254.0], np.float32)).astype(np.int32)
            cv2.fillPoly(mask, [px], 255)
        return mask
    observed_mask = raster(observed_norm)
    estimated_mask = raster(normalized)
    contact_mask = estimated_mask.copy() if verdict_status != "review" else np.zeros_like(estimated_mask)
    profile = calibration.camera_profile or {}
    diagnostics = (
        f"accepted_observations={len(accepted)}",
        f"tracked_observations={tracked_observations}",
        f"full_segmentation_refinements={full_refinements}",
        *(f"rejected_{key}={value}" for key, value in rejected.items()),
        f"fit_error_model_units={error:.3f}",
        f"apparent_scale_normalisation={fit_scale:.4f}",
        f"reconstruction_duration_ms={(time.perf_counter() - started) * 1000.0:.2f}",
        *(('low_fit_confidence',) if fit_confidence < .38 else ()),
    )
    report("complete", 100)
    return ReconstructionResult(
        _mesh(fitted),
        tuple((float(x), float(y)) for x, y in normalized),
        {"board_homography": homography.tolist(), "profile_used": bool(profile), "camera_profile": profile},
        fit_confidence,
        diagnostics,
        image,
        fit_variation,
        clean_image,
        observed_mask,
        estimated_mask,
        contact_mask,
        verdict_status,
    )
