from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class FramePacket:
    seq: int
    timestamp_ns: int
    jpeg: bytes
    width: int
    height: int
    wall_time_ns: int = 0

    @property
    def size_bytes(self) -> int:
        return len(self.jpeg)


@dataclass(frozen=True, slots=True)
class BufferStats:
    frame_count: int
    duration_seconds: float
    memory_bytes: int
    oldest_seq: int | None
    newest_seq: int | None


@dataclass(frozen=True, slots=True)
class CaptureStats:
    captured_frames: int
    encoded_frames: int
    capture_fps: float
    encode_fps: float
    queue_drops: int
    read_failures: int
    encode_failures: int
    average_encode_ms: float
    queue_depth: int
    source_description: str
    last_error: str


class AttemptState(str, Enum):
    COLLECTING = "Collecting"
    ENCODING = "Encoding"
    READY = "Ready"
    EXPORTING = "Exporting"
    EXPORTED = "Exported"
    ERROR = "Error"


class AttemptDecision(str, Enum):
    NOT_DECIDED = "Not decided"
    PENDING = "Not decided"  # backwards-compatible alias
    REVIEW = "Review"
    VALID = "Valid"
    FOUL = "Foul"
    PASSED = "Passed"
    MISSING = "Did not start"
    WITHDRAWN = "Withdrawn"
    REATTEMPT = "Reattempt"


@dataclass(slots=True)
class AttemptMarker:
    timestamp_ns: int
    label: str = "Marker"


@dataclass(slots=True)
class AttemptSession:
    attempt_id: int
    created_monotonic_ns: int
    created_wall_time: float
    freeze_timestamp_ns: int
    pre_seconds: float
    post_seconds: float
    expires_at_wall_time: float
    state: AttemptState = AttemptState.COLLECTING
    decision: AttemptDecision = AttemptDecision.NOT_DECIDED
    decision_wall_time: float = 0.0
    competitor_group: str = ""
    competitor_number: int = 0
    competitor_attempt_number: int = 0
    competition_phase: str = "qualification"
    rotation_completed: bool = False
    counts_for_rotation: bool = True
    packets: list[FramePacket] = field(default_factory=list)
    temp_video_path: Path | None = None
    temp_metadata_path: Path | None = None
    # Exported attempts are durable library items. Frozen attempts remain
    # temporary working media until the operator exports them.
    persistent: bool = False
    thumbnail_path: Path | None = None
    # Explicitly set when the operator opens Top-down Projection.  When absent,
    # the library falls back to Take-off Assist and then the frozen frame.
    thumbnail_frame_index: int | None = None
    export_path: Path | None = None
    evidence_raw_path: Path | None = None
    evidence_annotated_path: Path | None = None
    fps: float = 30.0
    frame_count: int = 0
    freeze_frame_index: int = 0
    takeoff_candidate_index: int | None = None
    takeoff_confidence: float = 0.0
    takeoff_analysis_start_ns: int | None = None
    takeoff_analysis_end_ns: int | None = None
    media_start_timestamp_ns: int = 0
    media_end_timestamp_ns: int = 0
    media_start_wall_time_ns: int = 0
    width: int = 0
    height: int = 0
    markers: list[AttemptMarker] = field(default_factory=list)
    error: str = ""
    quality_warning: str = ""
    protected: bool = False
    selected: bool = False
    adjudication_record_id: str = ""
    automatic_advisory: str = ""
    automatic_advisory_confidence: float = 0.0
    automatic_advisory_frame_index: int | None = None
    automatic_signed_clearance_cm: float | None = None
    automatic_uncertainty_cm: float | None = None
    automatic_advisory_reason: str = ""
    automatic_advisory_engine: str = ""
    automatic_analysis_ms: float = 0.0

    @property
    def start_timestamp_ns(self) -> int:
        if self.packets:
            return self.packets[0].timestamp_ns
        if self.media_start_timestamp_ns:
            return self.media_start_timestamp_ns
        return self.freeze_timestamp_ns - int(self.pre_seconds * 1_000_000_000)

    @property
    def end_timestamp_ns(self) -> int:
        if self.packets:
            return self.packets[-1].timestamp_ns
        if self.media_end_timestamp_ns:
            return self.media_end_timestamp_ns
        return self.freeze_timestamp_ns + int(self.post_seconds * 1_000_000_000)

    @property
    def duration_seconds(self) -> float:
        if self.frame_count > 1 and self.fps > 0:
            return (self.frame_count - 1) / self.fps
        return max(0.0, (self.end_timestamp_ns - self.start_timestamp_ns) / 1_000_000_000)

    @property
    def roster_label(self) -> str:
        if not self.competitor_group or self.competitor_number <= 0:
            return "Unassigned"
        suffix = f" · Try {self.competitor_attempt_number}" if self.competitor_attempt_number > 0 else ""
        return f"{self.competitor_group} #{self.competitor_number}{suffix}"

    def seconds_until_expiry(self, now_wall_time: float) -> float:
        return max(0.0, self.expires_at_wall_time - now_wall_time)


@dataclass(frozen=True, slots=True)
class MediaFrame:
    frame_bgr: object | None
    timestamp_ns: int
    frame_index: int
    frame_count: int
    fps: float


@dataclass(frozen=True, slots=True)
class TimelineModel:
    start_ns: int
    end_ns: int
    playhead_ns: int
    reference_ns: int
    freeze_ns: int | None = None
    markers_ns: Sequence[int] = ()
    available_start_ns: int | None = None
    available_end_ns: int | None = None
    is_live: bool = False
    wall_start_ns: int = 0
    assist_start_ns: int | None = None
    assist_end_ns: int | None = None
    predicted_frame_ns: int | None = None
    prediction_confidence: float = 0.0
