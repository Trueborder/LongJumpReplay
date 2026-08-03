from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np

from .models import FramePacket


@dataclass(frozen=True, slots=True)
class ExportResult:
    video_path: Path
    sidecar_path: Path | None
    frame_count: int
    fps: float
    duration_seconds: float
    codec: str


def decode_packet(packet: FramePacket) -> np.ndarray:
    array = np.frombuffer(packet.jpeg, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"Could not decode frame seq={packet.seq}")
    return frame


def estimate_fps(packets: Sequence[FramePacket], fallback: float = 30.0) -> float:
    if len(packets) < 2:
        return fallback
    duration = (packets[-1].timestamp_ns - packets[0].timestamp_ns) / 1_000_000_000
    if duration <= 0:
        return fallback
    return max(1.0, min(1000.0, (len(packets) - 1) / duration))




COMMON_VIDEO_FPS = (23.976, 24.0, 25.0, 29.97, 30.0, 50.0, 59.94, 60.0, 100.0, 119.88, 120.0, 240.0)


def normalise_video_fps(fps: float) -> float:
    """Return an encoder-friendly frame rate.

    OpenCV/FFmpeg can turn values such as 119.999 into a rational time base
    whose denominator exceeds MPEG-4's limit. Snap near-standard rates and
    otherwise round to two decimals so MP4 does not fail for harmless capture
    clock noise.
    """
    fps = max(1.0, min(1000.0, float(fps)))
    nearest = min(COMMON_VIDEO_FPS, key=lambda value: abs(value - fps))
    if abs(nearest - fps) <= 0.05:
        return nearest
    return round(fps, 2)

def _open_writer(base_path: Path, frame_size: tuple[int, int], fps: float, preferred_codec: str):
    attempts = [
        (preferred_codec, base_path.with_suffix(".mp4") if preferred_codec.lower() != "mjpg" else base_path.with_suffix(".avi")),
        ("mp4v", base_path.with_suffix(".mp4")),
        ("MJPG", base_path.with_suffix(".avi")),
    ]
    seen: set[tuple[str, str]] = set()
    for codec, path in attempts:
        key = (codec.upper(), path.suffix.lower())
        if key in seen:
            continue
        seen.add(key)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, frame_size)
        if writer.isOpened():
            return writer, path, codec
        writer.release()
    raise RuntimeError("No supported video encoder could be opened (tried mp4v and MJPG).")


def export_clip(
    packets: Sequence[FramePacket],
    output_directory: str | Path,
    preferred_codec: str = "mp4v",
    target_fps: float = 0.0,
    write_sidecar_json: bool = True,
    selected_seq: int | None = None,
    progress: Callable[[int, int], None] | None = None,
    base_name: str | None = None,
) -> ExportResult:
    if not packets:
        raise ValueError("No frames were supplied for export")
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
    base_path = output_directory / (base_name or f"jump_{timestamp}")

    first = decode_packet(packets[0])
    height, width = first.shape[:2]
    fps = normalise_video_fps(target_fps if target_fps > 0 else estimate_fps(packets))
    writer, video_path, used_codec = _open_writer(base_path, (width, height), fps, preferred_codec)
    try:
        for index, packet in enumerate(packets):
            frame = first if index == 0 else decode_packet(packet)
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            writer.write(frame)
            if progress:
                progress(index + 1, len(packets))
    finally:
        writer.release()

    duration = ((packets[-1].timestamp_ns - packets[0].timestamp_ns) / 1_000_000_000 if len(packets) > 1 else 0.0)
    sidecar_path: Path | None = None
    if write_sidecar_json:
        sidecar_path = base_path.with_suffix(".json")
        metadata = {
            "video_file": video_path.name,
            "created_local": datetime.now().astimezone().isoformat(),
            "frame_count": len(packets),
            "fps": fps,
            "duration_seconds": duration,
            "codec": used_codec,
            "first_seq": packets[0].seq,
            "last_seq": packets[-1].seq,
            "selected_seq": selected_seq,
            "first_timestamp_ns_monotonic": packets[0].timestamp_ns,
            "last_timestamp_ns_monotonic": packets[-1].timestamp_ns,
        }
        sidecar_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    return ExportResult(video_path, sidecar_path, len(packets), fps, duration, used_codec)


def save_frame_png(packet: FramePacket, output_directory: str | Path, prefix: str = "frame") -> Path:
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
    path = output_directory / f"{prefix}_{timestamp}_seq-{packet.seq}.png"
    if not cv2.imwrite(str(path), decode_packet(packet)):
        raise RuntimeError(f"Could not save frame to {path}")
    return path


def save_bgr_png(frame_bgr: np.ndarray, output_directory: str | Path, prefix: str = "frame") -> Path:
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
    path = output_directory / f"{prefix}_{timestamp}.png"
    if not cv2.imwrite(str(path), frame_bgr):
        raise RuntimeError(f"Could not save frame to {path}")
    return path
