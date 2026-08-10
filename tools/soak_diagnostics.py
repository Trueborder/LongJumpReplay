from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.capture import CaptureEngine
from src.config import BufferConfig, CameraConfig
from src.ring_buffer import TimeRingBuffer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded Long Jump Replay capture stability check")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--fps", type=float, default=120.0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def run(seconds: float, fps: float, width: int, height: int) -> tuple[dict[str, object], int]:
    if seconds <= 0 or fps <= 0 or width <= 0 or height <= 0:
        raise ValueError("seconds, fps, width, and height must be positive")
    camera = CameraConfig(source_type="synthetic", width=width, height=height, fps=fps)
    buffer_config = BufferConfig(duration_seconds=min(15.0, max(2.0, seconds)), max_memory_mb=1024, encoder_queue_size=128)
    ring = TimeRingBuffer(buffer_config.duration_seconds, buffer_config.max_memory_mb)
    capture = CaptureEngine(camera, buffer_config, ring)
    samples: list[dict[str, object]] = []
    started = time.monotonic()
    capture.start()
    try:
        next_sample = started + 1.0
        deadline = started + seconds
        while time.monotonic() < deadline:
            time.sleep(min(.1, max(0.0, deadline - time.monotonic())))
            if time.monotonic() >= next_sample:
                samples.append(asdict(capture.stats()))
                next_sample += 1.0
    finally:
        alive = capture.stop(timeout=3.0)
    final = asdict(capture.stats())
    capture_rates = [float(sample["capture_fps"]) for sample in samples if float(sample["capture_fps"]) > 0]
    encoded_rates = [float(sample["encode_fps"]) for sample in samples if float(sample["encode_fps"]) > 0]
    target_met = bool(capture_rates) and statistics.fmean(capture_rates) >= fps * .9
    passed = target_met and int(final["queue_drops"]) == 0 and int(final["encode_failures"]) == 0 and not alive
    report: dict[str, object] = {
        "kind": "synthetic_capture_soak",
        "requested": {"seconds": seconds, "fps": fps, "width": width, "height": height},
        "elapsed_seconds": time.monotonic() - started,
        "average_capture_fps": statistics.fmean(capture_rates) if capture_rates else 0.0,
        "average_encode_fps": statistics.fmean(encoded_rates) if encoded_rates else 0.0,
        "final": final,
        "buffer": asdict(ring.stats()),
        "remaining_workers": alive,
        "acceptance": {"capture_at_least_90_percent": target_met, "zero_queue_drops": int(final["queue_drops"]) == 0, "passed": passed},
    }
    return report, 0 if passed else 1


def main() -> int:
    args = parse_args()
    report, exit_code = run(args.seconds, args.fps, args.width, args.height)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
