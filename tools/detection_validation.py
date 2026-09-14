from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.models import FramePacket
from src.takeoff_assist import detect_takeoff_candidate
from src.automatic_takeoff import analyse_attempt
from src.top_view_projection import ProjectionCalibration


def packets_from_video(path: Path) -> tuple[list[FramePacket], float]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open validation clip: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    packets: list[FramePacket] = []
    index = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok: break
            encoded_ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not encoded_ok: raise RuntimeError(f"Cannot encode frame {index}")
            timestamp = int(index / fps * 1_000_000_000)
            packets.append(FramePacket(index, timestamp, jpeg.tobytes(), frame.shape[1], frame.shape[0], timestamp))
            index += 1
    finally:
        cap.release()
    return packets, fps


def validate(manifest_path: Path) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema_version = int(manifest.get("schema_version", 0))
    if schema_version not in {1, 2}:
        raise ValueError("Unsupported validation manifest schema")
    results = []
    passed = 0
    for case in manifest.get("cases", []):
        clip = Path(case["clip"])
        if not clip.is_absolute(): clip = manifest_path.parent / clip
        packets, fps = packets_from_video(clip)
        freeze_frame = int(case["freeze_frame"])
        expected = int(case["expected_takeoff_frame"])
        tolerance = int(case.get("tolerance_frames", 1))
        started = time.perf_counter()
        if schema_version == 1:
            candidate = detect_takeoff_candidate(
                packets, packets[freeze_frame].timestamp_ns, tuple(case["roi"]),
                float(case.get("before_seconds", 2.5)), float(case.get("after_seconds", .25)),
                int(case.get("target_width", 240)),
            )
            actual = None if candidate is None else int(candidate.frame_index)
            actual_advisory = None
            confidence = None if candidate is None else candidate.confidence
            signed_clearance_cm = None
            frame_ok = actual is not None and abs(actual - expected) <= tolerance
            advisory_ok = True
        else:
            calibration = ProjectionCalibration(
                tuple(tuple(map(float, point)) for point in case["board_corners"]),
                tuple(tuple(map(float, point)) for point in case["foul_line"]),
                reference_width=packets[0].width, reference_height=packets[0].height,
                pad_length_cm=float(case.get("pad_length_cm", 120.1)),
                pad_width_cm=float(case.get("pad_width_cm", 34.0)),
                legal_side_flipped=bool(case.get("legal_side_flipped", False)),
            )
            advisory = analyse_attempt(
                packets, packets[freeze_frame].timestamp_ns, tuple(case["roi"]), calibration,
                before_seconds=float(case.get("before_seconds", .7)),
                after_seconds=float(case.get("after_seconds", .32)),
                target_width=int(case.get("target_width", 192)),
            )
            actual = int(advisory.frame_index)
            actual_advisory = advisory.status.value
            confidence = advisory.confidence
            signed_clearance_cm = advisory.signed_clearance_cm
            frame_ok = abs(actual - expected) <= tolerance
            advisory_ok = actual_advisory == str(case["expected_advisory"]).lower()
        ok = frame_ok and advisory_ok
        passed += int(ok)
        results.append({
            "id": case["id"], "passed": ok, "expected": expected, "actual": actual,
            "expected_advisory": case.get("expected_advisory"), "actual_advisory": actual_advisory,
            "confidence": None if confidence is None else round(float(confidence), 4),
            "signed_clearance_cm": signed_clearance_cm,
            "tolerance_frames": tolerance, "fps": fps,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        })
    return {
        "dataset_version": manifest["dataset_version"],
        "algorithm_version": manifest.get("algorithm_version", "working-tree"),
        "passed": passed, "total": len(results), "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the versioned LongJumpReplay take-off validation dataset")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = validate(args.manifest.resolve())
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output: args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
