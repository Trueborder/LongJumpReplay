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
    if int(manifest.get("schema_version", 0)) != 1:
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
        candidate = detect_takeoff_candidate(
            packets, packets[freeze_frame].timestamp_ns, tuple(case["roi"]),
            float(case.get("before_seconds", 2.5)), float(case.get("after_seconds", .25)),
            int(case.get("target_width", 240)),
        )
        actual = None if candidate is None else int(candidate.frame_index)
        ok = actual is not None and abs(actual - expected) <= tolerance
        passed += int(ok)
        results.append({
            "id": case["id"], "passed": ok, "expected": expected, "actual": actual,
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
