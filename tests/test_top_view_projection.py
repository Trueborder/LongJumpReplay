import cv2
import numpy as np

from src.board_calibration_wizard import foul_band_from_line, foul_line_from_band


def test_editable_foul_band_preserves_the_projection_centreline():
    line = ((120.0, 80.0), (130.0, 410.0))
    band = foul_band_from_line(line, (640, 480), thickness_px=10)
    restored = foul_line_from_band(band, (640, 480))
    assert len(band) == 4
    assert np.allclose(restored, line, atol=1e-4)


def test_brush_trace_snaps_to_nearby_shoe_edge():
    frame = np.full((180, 320, 3), 210, np.uint8)
    cv2.ellipse(frame, (165, 92), (82, 34), -8, 0, 360, (25, 45, 85), -1)
    rough = ((82, 72), (155, 52), (247, 76), (238, 119), (150, 130), (76, 108))
    snapped = snap_brush_trace_to_edges(frame, rough, radius_px=18, samples=24)
    assert len(snapped) == 24
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 35, 110)
    distance = cv2.distanceTransform(255-edges, cv2.DIST_L2, 3)
    values = [distance[min(179, max(0, round(y))), min(319, max(0, round(x)))] for x, y in snapped]
    assert float(np.median(values)) < 3.0
import pytest
from threading import Event

from src.models import FramePacket
from src.top_view_projection import (
    ProjectionCalibration,
    TopViewProjectionWindow,
    board_search_roi,
    calibration_matches,
    consecutive_candidate_indices,
    compute_pad_homography,
    create_projection_calibration,
    detect_board_corners,
    detect_foul_line,
    estimate_foot_polygon,
    estimated_footprint,
    filter_projection_candidates,
    measure_projected_foot,
    measurement_uncertainty_cm,
    order_board_corners,
    project_points_to_pad,
    projection_verdict_text,
    rank_decoded_projection_frames,
    rank_projection_candidates,
    render_board_projection_image,
    snap_brush_trace_to_edges,
    smooth_closed_outline,
    unproject_points_from_pad,
)
from src.shoe_reconstruction import (
    ReconstructionCancelled,
    ReconstructionTimedOut,
    _track_outline_between_frames,
    reconstruct_shoe_overhead,
)


def _packet(frame: np.ndarray, index: int) -> FramePacket:
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    return FramePacket(index, index * 10_000_000, encoded.tobytes(), frame.shape[1], frame.shape[0])


def test_neighbour_outline_tracking_follows_frame_translation():
    source = np.full((180, 320, 3), 180, np.uint8)
    cv2.rectangle(source, (95, 65), (225, 125), (25, 55, 105), -1)
    for x in range(105, 220, 14):
        cv2.line(source, (x, 70), (x + 8, 120), (210, 225, 235), 2)
    translation = np.asarray([[1, 0, 7], [0, 1, -4]], np.float32)
    target = cv2.warpAffine(source, translation, (320, 180), borderValue=(180, 180, 180))
    outline = np.asarray(((95, 65), (225, 65), (225, 125), (95, 125)), np.float32)

    tracked = _track_outline_between_frames(source, target, outline)

    assert tracked is not None
    assert np.allclose(np.median(tracked - outline, axis=0), (7, -4), atol=1.5)


def test_pad_homography_maps_corners_and_measurement_to_normalized_coordinates():
    corners = ((.15, .20), (.85, .16), (.92, .82), (.10, .88))
    homography = compute_pad_homography(corners, (1000, 800), (900, 300))
    assert homography.shape == (3, 3)
    projected = project_points_to_pad(((150, 160), (850, 128), (920, 656), (100, 704)), corners, (1000, 800))
    assert np.allclose(projected, ((0, 0), (1, 0), (1, 1), (0, 1)), atol=.01)
    restored = unproject_points_from_pad(projected, corners, (1000, 800))
    assert np.allclose(restored, ((150, 160), (850, 128), (920, 656), (100, 704)), atol=.1)

    calibration = ProjectionCalibration(corners, ((.0, .82), (1.0, .82)), "camera", 1000, 800, 100, 20)
    measurement = measure_projected_foot(((450, 650), (550, 650), (550, 700), (450, 700)), calibration, (1000, 800))
    assert measurement.distance_to_foul_line_cm is not None
    assert measurement.distance_to_foul_line_cm >= 0


def test_foul_line_is_projected_from_camera_coordinates_with_the_pad():
    corners = ((.2, .2), (.8, .2), (.8, .8), (.2, .8))
    calibration = ProjectionCalibration(corners, ((.2, .5), (.8, .5)), "camera", 1000, 1000, 100, 20)
    measurement = measure_projected_foot(((400, 450), (600, 450), (600, 480), (400, 480)), calibration, (1000, 1000))
    # Nearest sole edge, not the centre, is 1.67 cm from this line.
    assert measurement.distance_to_foul_line_cm == pytest.approx(1.67, abs=.1)
    assert measurement.signed_clearance_cm < 0
    assert measurement.status == "over"


def test_board_setup_accepts_corners_in_any_order_and_needs_no_lengths():
    clicked = ((800, 800), (200, 200), (200, 800), (800, 200))
    ordered = order_board_corners(clicked)
    assert np.allclose(ordered, ((200, 200), (800, 200), (800, 800), (200, 800)))

    calibration = create_projection_calibration(clicked, ((200, 500), (800, 500)), (1000, 1000), "camera")
    assert calibration.pad_length_cm == 120.1
    assert calibration.pad_width_cm == 34
    assert calibration.shoe_width_cm == 0
    assert np.allclose(calibration.board_corners, ((.2, .2), (.8, .2), (.8, .8), (.2, .8)))

    old_default = ProjectionCalibration(calibration.board_corners, calibration.foul_line, pad_length_cm=122, pad_width_cm=20)
    migrated = create_projection_calibration(clicked, ((200, 500), (800, 500)), (1000, 1000), "camera", old_default)
    assert (migrated.pad_length_cm, migrated.pad_width_cm) == (120.1, 34.0)


def test_calibrated_board_search_area_expands_beyond_the_settings_roi():
    roi = board_search_roi(((.32, .01), (.85, .02), (.99, .90), (.62, .92)))
    assert roi[0] < .32
    assert roi[0] + roi[2] == pytest.approx(1.0)
    assert roi[1] == 0.0
    assert roi[1] + roi[3] > .95


def test_candidate_ranking_is_bounded_and_decodes_local_frames():
    frames = []
    for index in range(20):
        frame = np.zeros((120, 200, 3), dtype=np.uint8)
        cv2.rectangle(frame, (60 + index, 50), (92 + index, 82), (220, 220, 220), -1)
        frames.append(_packet(frame, index))
    candidates = rank_projection_candidates(frames, 100_000_000, (0.2, 0.2, 0.7, 0.7))
    assert 1 <= len(candidates) <= 7
    assert all(candidate.frame_bgr.shape == (120, 200, 3) for candidate in candidates)


def test_classical_motion_estimator_returns_a_polygon_without_ai():
    reference = np.zeros((160, 240, 3), dtype=np.uint8)
    current = reference.copy()
    cv2.rectangle(current, (80, 65), (130, 100), (230, 230, 230), -1)
    estimate = estimate_foot_polygon(current, [reference], (0.1, 0.2, 0.8, 0.7))
    assert estimate is not None
    assert len(estimate.polygon_px) >= 3
    assert 0 <= estimate.confidence <= 1


def test_foot_estimator_rejects_a_large_ground_shadow():
    reference = np.full((180, 280, 3), (150, 175, 205), dtype=np.uint8)
    current = reference.copy()
    shadow_colour = tuple(int(value * .72) for value in (150, 175, 205))
    cv2.ellipse(current, (105, 118), (92, 34), 0, 0, 360, shadow_colour, -1)
    cv2.rectangle(current, (160, 66), (225, 101), (20, 25, 30), -1)
    estimate = estimate_foot_polygon(
        current,
        [reference, reference],
        (0, 0, 1, 1),
        ((0, 0), (1, 0), (1, 1), (0, 1)),
    )
    assert estimate is not None
    xs = [point[0] for point in estimate.polygon_px]
    ys = [point[1] for point in estimate.polygon_px]
    assert min(xs) >= 150
    assert max(ys) <= 110


def test_candidate_ranking_prefers_the_takeoff_time_over_a_large_shadow():
    target_ns = 1_000_000_000
    frames = []
    for index, offset_ms in enumerate((-60, -40, -20, 0, 20, 40, 60)):
        frame = np.full((140, 220, 3), (145, 170, 200), dtype=np.uint8)
        if offset_ms == 0:
            cv2.rectangle(frame, (115, 48), (175, 83), (18, 25, 32), -1)
        elif offset_ms == 60:
            shadow_colour = tuple(int(value * .68) for value in (145, 170, 200))
            cv2.ellipse(frame, (105, 90), (95, 40), 0, 0, 360, shadow_colour, -1)
        frames.append((index, target_ns + offset_ms * 1_000_000, frame))
    candidates = rank_decoded_projection_frames(frames, target_ns, (0, 0, 1, 1))
    assert candidates[0].timestamp_ns == target_ns


def test_candidate_filter_hides_frames_without_a_shoe():
    reference = np.full((180, 320, 3), (145, 170, 200), np.uint8)
    cv2.rectangle(reference, (60, 105), (270, 130), (215, 220, 225), -1)
    shoe = reference.copy()
    cv2.ellipse(shoe, (165, 96), (30, 13), 0, 0, 360, (18, 24, 31), -1)
    ranked = rank_decoded_projection_frames(((0, 0, reference), (1, 10_000_000, shoe)), 10_000_000, (0, 0, 1, 1))
    kept, estimates = filter_projection_candidates(ranked, (reference,), (0, 0, 1, 1), None)
    assert [candidate.frame_index for candidate in kept] == [1]
    assert 1 in estimates


def test_calibration_matches_camera_and_frame_identity():
    calibration = ProjectionCalibration(((0, 0), (1, 0), (1, 1), (0, 1)), ((0, .8), (1, .8)), "camera-0", 640, 480)
    assert calibration_matches(calibration, "camera-0", (640, 480))
    assert not calibration_matches(calibration, "camera-1", (640, 480))
    assert not calibration_matches(calibration, "camera-0", (1280, 720))


def test_optional_shoe_width_creates_a_planar_estimated_envelope():
    calibration = ProjectionCalibration(((0, 0), (1, 0), (1, 1), (0, 1)), ((0, .8), (1, .8)), shoe_width_cm=10, pad_width_cm=20)
    footprint = estimated_footprint(((.2, .4), (.8, .45), (.75, .55), (.25, .5)), calibration)
    assert len(footprint) == 4
    assert footprint[0][0] == pytest.approx(.2)
    assert footprint[1][0] == pytest.approx(.8)
    assert footprint[2][1] - footprint[0][1] == pytest.approx(.5)


def test_physical_long_axis_follows_horizontal_or_vertical_foul_line():
    corners = ((.2, .2), (.8, .2), (.8, .8), (.2, .8))
    horizontal = ProjectionCalibration(corners, ((.2, .8), (.8, .8)), pad_length_cm=120.1, pad_width_cm=34)
    vertical = ProjectionCalibration(corners, ((.8, .2), (.8, .8)), pad_length_cm=120.1, pad_width_cm=34)
    horizontal_result = measure_projected_foot(((400, 620), (600, 620), (600, 650), (400, 650)), horizontal, (1000, 1000))
    vertical_result = measure_projected_foot(((620, 400), (650, 400), (650, 600), (620, 600)), vertical, (1000, 1000))
    assert horizontal_result.signed_clearance_cm == pytest.approx(vertical_result.signed_clearance_cm, abs=.05)
    assert horizontal_result.signed_clearance_cm > 0


def test_signed_clearance_touching_crossing_and_persisted_flip():
    calibration = ProjectionCalibration(((0, 0), (1, 0), (1, 1), (0, 1)), ((0, .8), (1, .8)), pad_length_cm=120.1, pad_width_cm=34)
    clear = measure_projected_foot(((300, 650), (500, 650), (500, 740), (300, 740)), calibration, (1000, 1000), confidence=1)
    touching = measure_projected_foot(((300, 700), (500, 700), (500, 798), (300, 798)), calibration, (1000, 1000), confidence=1)
    over = measure_projected_foot(((300, 740), (500, 740), (500, 850), (300, 850)), calibration, (1000, 1000), confidence=1)
    flipped = measure_projected_foot(((300, 650), (500, 650), (500, 740), (300, 740)), ProjectionCalibration(
        calibration.board_corners, calibration.foul_line, pad_length_cm=120.1, pad_width_cm=34, legal_side_flipped=True,
    ), (1000, 1000), confidence=1)
    assert clear.status == "clear" and clear.display_text().startswith("+")
    assert touching.status == "touching" and touching.display_text().startswith("0.0 cm")
    assert over.status == "over" and over.signed_clearance_cm < 0
    assert flipped.signed_clearance_cm < 0
    assert projection_verdict_text(clear.status) == "VALID"
    assert projection_verdict_text(touching.status) == "ON THE LINE"
    assert projection_verdict_text(over.status) == "FOUL"


def test_uncertainty_combines_independent_sources():
    result = measurement_uncertainty_cm(.2, .3, .4, .1)
    assert result == pytest.approx((.2**2 + (.3 / np.sqrt(12))**2 + .4**2 + .1**2) ** .5)


def test_consecutive_candidates_are_unique_and_balanced_at_any_frame_rate():
    assert consecutive_candidate_indices(50, 100) == (47, 48, 49, 50, 51, 52, 53)
    assert consecutive_candidate_indices(1, 5) == (0, 1, 2, 3, 4)
    assert consecutive_candidate_indices(998, 1000) == (993, 994, 995, 996, 997, 998, 999)


def test_manual_recovery_guesses_editable_board_and_foul_line_handles():
    frame = np.zeros((400, 800, 3), dtype=np.uint8)
    board = TopViewProjectionWindow._manual_board_guess(frame, (.10, .20, .80, .60))
    foul = TopViewProjectionWindow._manual_foul_guess(board)
    assert len(board) == 4
    assert len(foul) == 2
    assert all(0 <= x < 800 and 0 <= y < 400 for x, y in (*board, *foul))
    assert np.linalg.norm(np.asarray(foul[1]) - np.asarray(foul[0])) > 100


def test_automatic_analysis_finds_board_foul_line_and_curved_shoe_outline():
    reference = np.full((360, 640, 3), 75, np.uint8)
    expected_board = np.asarray(((90, 100), (550, 115), (530, 270), (105, 255)), np.int32)
    cv2.fillConvexPoly(reference, expected_board, (215, 215, 215))
    cv2.line(reference, (98, 181), (540, 196), (30, 30, 30), 4)
    frame = reference.copy()
    cv2.ellipse(frame, (320, 185), (65, 22), 8, 0, 360, (18, 24, 31), -1)
    board = detect_board_corners(reference, (.05, .1, .9, .75))
    assert board is not None
    assert np.max(np.linalg.norm(np.asarray(board) - expected_board, axis=1)) < 12
    foul = detect_foul_line(reference, board)
    assert foul is not None
    assert 175 < np.mean(np.asarray(foul)[:, 1]) < 205
    calibration = create_projection_calibration(board, foul, (640, 360), "camera")
    estimate = estimate_foot_polygon(frame, [reference], (.05, .1, .9, .75), calibration.board_corners, calibration.foul_line)
    assert estimate is not None
    curved = smooth_closed_outline(estimate.polygon_px, 20)
    assert len(curved) == 20
    rendered = render_board_projection_image(frame, calibration, curved, estimate.confidence)
    assert rendered.shape == (330, 720, 3)


def test_local_reconstruction_returns_mesh_and_overhead_image():
    frame = np.full((300, 600, 3), 180, np.uint8)
    reference = frame.copy()
    cv2.rectangle(frame, (250, 120), (370, 180), (20, 30, 40), -1)
    calibration = ProjectionCalibration(((0, 0), (1, 0), (1, 1), (0, 1)), ((0, .75), (1, .75)), pad_length_cm=120.1, pad_width_cm=34)
    outline = ((250, 120), (370, 120), (370, 180), (250, 180))
    stages = []
    result = reconstruct_shoe_overhead(frame, outline, [(0, frame)], [reference], calibration, progress=lambda stage, value: stages.append((stage, value)))
    assert result.fit_confidence >= .38
    assert len(result.mesh_geometry.vertices) > 20
    assert result.overhead_image.shape == (255, 900, 3)
    assert stages[-1] == ("complete", 100)


def test_reconstruction_timeout_and_cancellation_do_not_fabricate_results():
    frame = np.full((100, 200, 3), 180, np.uint8)
    calibration = ProjectionCalibration(((0, 0), (1, 0), (1, 1), (0, 1)), ((0, .8), (1, .8)), pad_length_cm=120.1, pad_width_cm=34)
    outline = ((60, 35), (130, 35), (130, 65), (60, 65))
    with pytest.raises(ReconstructionTimedOut):
        reconstruct_shoe_overhead(frame, outline, [], [], calibration, time_limit_seconds=0)
    cancelled = Event(); cancelled.set()
    with pytest.raises(ReconstructionCancelled):
        reconstruct_shoe_overhead(frame, outline, [], [], calibration, cancel=cancelled)


def test_reconstruction_normalises_apparent_size_instead_of_rejecting_it():
    frame = np.full((300, 600, 3), 180, np.uint8)
    calibration = ProjectionCalibration(((0, 0), (1, 0), (1, 1), (0, 1)), ((0, .8), (1, .8)), pad_length_cm=120.1, pad_width_cm=34)
    result = reconstruct_shoe_overhead(frame, ((250, 120), (258, 120), (258, 124), (250, 124)), [], [], calibration)
    assert result.overhead_image.size > 0
    assert any(item.startswith("apparent_scale_normalisation=") for item in result.diagnostics)
