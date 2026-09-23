from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
import json
from pathlib import Path
from queue import Queue
import shutil
from threading import Event, RLock, Thread
import time
from typing import Iterable

import cv2

from .config import AttemptsConfig, ExportConfig
from .exporter import decode_packet, estimate_fps, export_clip
from .models import AttemptDecision, AttemptMarker, AttemptSession, AttemptState, FramePacket, MediaFrame
from .ring_buffer import TimeRingBuffer


class AttemptManager:
    """Create durable replay sessions from the rolling live buffer.

    A freeze immediately copies the pre-roll JPEG packets, continues collecting
    post-roll packets, then encodes the completed session into temporary video.
    The copied packets mean a decision can take longer than the live buffer.
    """

    POST_ROLL_STALL_GRACE_SECONDS = 3.0
    CACHE_SIZE_CACHE_SECONDS = 0.5
    # Frame stepping, Take-off Assist and Top-down Projection often revisit the
    # same small neighbourhood. Twelve 720p frames are still bounded, but avoid
    # repeatedly JPEG-decoding those frames across tools.
    DECODE_CACHE_FRAMES = 12

    def __init__(
        self,
        ring_buffer: TimeRingBuffer,
        config: AttemptsConfig,
        export_config: ExportConfig,
        cache_directory: Path,
        event_queue: Queue[tuple[str, object]],
        persistent_directory: Path | None = None,
    ) -> None:
        self.ring_buffer = ring_buffer
        self.config = config
        self.export_config = export_config
        self.cache_directory = cache_directory
        self.persistent_directory = persistent_directory or cache_directory / "recordings"
        self.event_queue = event_queue
        self._lock = RLock()
        self._attempts: list[AttemptSession] = []
        self._next_id = 1
        self._stop = Event()
        self._thread: Thread | None = None
        self._workers: dict[str, Thread] = {}
        self._pending_exports: dict[int, Path] = {}
        self._video_caps: dict[int, cv2.VideoCapture] = {}
        self._frame_cache: dict[int, OrderedDict[int, tuple[object, int]]] = {}
        self._video_next_index: dict[int, int] = {}
        self._cancelled_attempt_ids: set[int] = set()
        self._cache_size_value: int | None = None
        self._cache_size_checked_at = 0.0
    def start(self) -> None:
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self.persistent_directory.mkdir(parents=True, exist_ok=True)
        self._recover_cache_index()
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="attempt-manager", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> list[str]:
        self._stop.set()
        deadline = time.perf_counter() + max(.1, timeout)
        if self._thread and self._thread.is_alive():
            self._thread.join(max(.0, deadline - time.perf_counter()))
        with self._lock:
            self._cancelled_attempt_ids.update(a.attempt_id for a in self._attempts if not a.persistent)
            workers = list(self._workers.items())
            for cap in self._video_caps.values():
                cap.release()
            self._video_caps.clear()
            self._frame_cache.clear()
            self._video_next_index.clear()
        # Codec and copy workers are allowed to finish, but never outlive the
        # requested shutdown budget. This also prevents test/session builds from
        # accumulating OpenCV workers across repeated window launches.
        for _name, worker in workers:
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            if worker.is_alive():
                worker.join(remaining)
        alive = []
        if self._thread and self._thread.is_alive():
            alive.append(self._thread.name)
        with self._lock:
            alive.extend(name for name, worker in self._workers.items() if worker.is_alive())
        return alive

    def create_attempt(
        self,
        freeze_timestamp_ns: int | None = None,
        competitor_group: str = "",
        competitor_number: int = 0,
        competitor_attempt_number: int = 0,
        quality_warning: str = "",
        competition_phase: str = "qualification",
    ) -> AttemptSession | None:
        newest = self.ring_buffer.newest()
        if newest is None:
            return None
        freeze_ns = freeze_timestamp_ns or newest.timestamp_ns
        start_ns = freeze_ns - int(self.config.pre_seconds * 1_000_000_000)
        packets = self.ring_buffer.snapshot_between(start_ns, freeze_ns)
        if not packets:
            packets = [newest]
        now = time.time()
        with self._lock:
            for attempt in self._attempts:
                attempt.selected = False
            freeze_index = min(range(len(packets)), key=lambda i: abs(packets[i].timestamp_ns - freeze_ns))
            attempt = AttemptSession(
                attempt_id=self._next_id,
                created_monotonic_ns=time.monotonic_ns(),
                created_wall_time=now,
                freeze_timestamp_ns=freeze_ns,
                pre_seconds=self.config.pre_seconds,
                post_seconds=self.config.post_seconds,
                expires_at_wall_time=now + self.config.retention_minutes * 60,
                packets=list(packets),
                frame_count=len(packets),
                freeze_frame_index=freeze_index,
                fps=estimate_fps(packets, fallback=30.0),
                width=packets[0].width,
                height=packets[0].height,
                media_start_timestamp_ns=packets[0].timestamp_ns,
                media_end_timestamp_ns=packets[-1].timestamp_ns,
                selected=self.config.auto_select_new,
                competitor_group=competitor_group,
                competitor_number=competitor_number,
                competitor_attempt_number=competitor_attempt_number,
                competition_phase=competition_phase,
                quality_warning=quality_warning,
            )
            self._next_id += 1
            self._attempts.append(attempt)
            self._enforce_limits_locked()
        self.event_queue.put(("attempt_created", attempt.attempt_id))
        return self.get_attempt(attempt.attempt_id)


    def create_placeholder_attempt(
        self,
        competitor_group: str,
        competitor_number: int,
        competitor_attempt_number: int,
        decision: AttemptDecision,
        competition_phase: str = "qualification",
    ) -> AttemptSession:
        """Create a roster result without video (Pass, DNS, Withdrawn)."""
        now = time.time()
        with self._lock:
            for existing in self._attempts:
                existing.selected = False
            attempt = AttemptSession(
                attempt_id=self._next_id,
                created_monotonic_ns=time.monotonic_ns(),
                created_wall_time=now,
                freeze_timestamp_ns=time.monotonic_ns(),
                pre_seconds=0.0,
                post_seconds=0.0,
                expires_at_wall_time=now + self.config.retention_minutes * 60,
                state=AttemptState.READY,
                decision=AttemptDecision(decision),
                decision_wall_time=now,
                competitor_group=competitor_group,
                competitor_number=competitor_number,
                competitor_attempt_number=competitor_attempt_number,
                competition_phase=competition_phase,
                rotation_completed=True,
                counts_for_rotation=decision is not AttemptDecision.REATTEMPT,
                selected=True,
            )
            self._next_id += 1
            self._attempts.append(attempt)
            self._write_metadata_locked(attempt)
            self._enforce_limits_locked()
        self.event_queue.put(("attempt_created", attempt.attempt_id))
        self.event_queue.put(("attempt_ready", attempt.attempt_id))
        return self.get_attempt(attempt.attempt_id)  # type: ignore[return-value]

    def set_rotation_completed(self, attempt_id: int, completed: bool = True) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None:
                return False
            attempt.rotation_completed = bool(completed)
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True

    def set_counts_for_rotation(self, attempt_id: int, counts: bool) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None:
                return False
            attempt.counts_for_rotation = bool(counts)
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True

    def attempts(self) -> list[AttemptSession]:
        with self._lock:
            return [self._public_copy(a) for a in self._attempts]

    def get_attempt(self, attempt_id: int) -> AttemptSession | None:
        with self._lock:
            found = self._find_locked(attempt_id)
            return self._public_copy(found) if found else None

    def selected_attempt(self) -> AttemptSession | None:
        with self._lock:
            found = next((a for a in self._attempts if a.selected), None)
            return self._public_copy(found) if found else None

    def clear_selection(self) -> None:
        with self._lock:
            for attempt in self._attempts:
                if attempt.selected:
                    attempt.selected = False
                    attempt.expires_at_wall_time = max(
                        attempt.expires_at_wall_time,
                        time.time() + self.config.retention_minutes * 60,
                    )
        self.event_queue.put(("attempt_selected", 0))

    def select(self, attempt_id: int) -> AttemptSession | None:
        with self._lock:
            target = self._find_locked(attempt_id)
            if target is None:
                return None
            for attempt in self._attempts:
                attempt.selected = attempt.attempt_id == attempt_id
            # A selected attempt is never deleted under the operator's cursor.
            target.expires_at_wall_time = max(target.expires_at_wall_time, time.time() + 30.0)
            result = self._public_copy(target)
        self.event_queue.put(("attempt_selected", attempt_id))
        return result

    def select_relative(self, delta: int) -> AttemptSession | None:
        with self._lock:
            if not self._attempts:
                return None
            current = next((i for i, a in enumerate(self._attempts) if a.selected), len(self._attempts) - 1)
            index = max(0, min(len(self._attempts) - 1, current + delta))
            target_id = self._attempts[index].attempt_id
        return self.select(target_id)

    def add_marker(self, attempt_id: int, timestamp_ns: int, label: str = "Marker") -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None:
                return False
            attempt.markers.append(AttemptMarker(timestamp_ns, label))
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True


    def packets_snapshot(self, attempt_id: int) -> list[FramePacket]:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            return list(attempt.packets) if attempt else []

    def set_decision(self, attempt_id: int, decision: AttemptDecision) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None:
                return False
            attempt.decision = AttemptDecision(decision)
            attempt.decision_wall_time = time.time()
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True

    def set_adjudication_record_id(self, attempt_id: int, record_id: str) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None:
                return False
            attempt.adjudication_record_id = str(record_id)
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True

    def set_evidence_paths(self, attempt_id: int, raw_path: Path | None, annotated_path: Path | None) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None:
                return False
            attempt.evidence_raw_path = raw_path
            attempt.evidence_annotated_path = annotated_path
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True

    def set_takeoff_candidate(
        self,
        attempt_id: int,
        frame_index: int,
        confidence: float,
        analysis_start_ns: int | None = None,
        analysis_end_ns: int | None = None,
    ) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None or attempt.frame_count <= 0:
                return False
            attempt.takeoff_candidate_index = max(0, min(attempt.frame_count - 1, int(frame_index)))
            attempt.takeoff_confidence = max(0.0, min(1.0, float(confidence)))
            if analysis_start_ns is not None and analysis_end_ns is not None:
                lower, upper = attempt.start_timestamp_ns, attempt.end_timestamp_ns
                start = max(lower, min(upper, int(analysis_start_ns)))
                end = max(lower, min(upper, int(analysis_end_ns)))
                attempt.takeoff_analysis_start_ns = min(start, end)
                attempt.takeoff_analysis_end_ns = max(start, end)
            self._write_metadata_locked(attempt)
        self.event_queue.put(("takeoff_candidate", (attempt_id, attempt.takeoff_candidate_index, attempt.takeoff_confidence)))
        return True

    def set_automatic_advisory(
        self, attempt_id: int, status: str, confidence: float, frame_index: int,
        signed_clearance_cm: float | None, uncertainty_cm: float | None,
        reason: str, engine: str, elapsed_ms: float,
    ) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None or attempt.frame_count <= 0:
                return False
            attempt.automatic_advisory = str(status)
            attempt.automatic_advisory_confidence = max(0.0, min(1.0, float(confidence)))
            attempt.automatic_advisory_frame_index = max(0, min(attempt.frame_count - 1, int(frame_index)))
            attempt.automatic_signed_clearance_cm = None if signed_clearance_cm is None else float(signed_clearance_cm)
            attempt.automatic_uncertainty_cm = None if uncertainty_cm is None else max(0.0, float(uncertainty_cm))
            attempt.automatic_advisory_reason = str(reason)
            attempt.automatic_advisory_engine = str(engine)
            attempt.automatic_analysis_ms = max(0.0, float(elapsed_ms))
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True

    def set_thumbnail_frame(self, attempt_id: int, frame_index: int) -> bool:
        """Persist the operator's preferred library thumbnail frame."""
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None or attempt.frame_count <= 0:
                return False
            attempt.thumbnail_frame_index = max(0, min(attempt.frame_count - 1, int(frame_index)))
            self._write_metadata_locked(attempt)
        self.event_queue.put(("attempt_updated", attempt_id))
        return True

    def prepare_for_shutdown(self, retain_recordings: bool) -> None:
        """Finish current session recordings before the application closes.

        The live RAM buffer remains temporary. When recordings are retained,
        frozen attempts are promoted to the session recording directory and
        active encodes are allowed to finish there.
        """
        encode_ids: list[int] = []
        with self._lock:
            for attempt in self._attempts:
                if not retain_recordings:
                    self._cancelled_attempt_ids.add(attempt.attempt_id)
                    continue
                attempt.persistent = True
                if attempt.state is AttemptState.COLLECTING:
                    attempt.state = AttemptState.ENCODING
                    encode_ids.append(attempt.attempt_id)
                elif attempt.state is AttemptState.READY and attempt.temp_video_path and attempt.temp_video_path.exists():
                    destination = self.persistent_directory / attempt.temp_video_path.name.replace("attempt_", "recording_", 1)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        attempt.temp_video_path.replace(destination)
                        attempt.temp_video_path = destination
                    except OSError:
                        attempt.persistent = False
                self._write_metadata_locked(attempt)
        for attempt_id in encode_ids:
            self._submit_encode(attempt_id)
    def clear_all(self) -> int:
        """Remove every temporary attempt, including selected records.

        Encoding workers are not killed mid-codec call. Their attempt IDs are
        cancelled, so any late output is deleted instead of reappearing.
        """
        with self._lock:
            attempts = [a for a in self._attempts if not a.persistent]
            attempt_ids = {a.attempt_id for a in attempts}
            self._cancelled_attempt_ids.update(attempt_ids)
            for attempt_id in attempt_ids:
                self._pending_exports.pop(attempt_id, None)
                cap = self._video_caps.pop(attempt_id, None)
                if cap is not None:
                    cap.release()
                self._frame_cache.pop(attempt_id, None)
                self._video_next_index.pop(attempt_id, None)
            self._attempts = [a for a in self._attempts if a.persistent]
            for attempt in attempts:
                for path in (attempt.temp_video_path, attempt.temp_metadata_path):
                    if path:
                        try: path.unlink(missing_ok=True)
                        except OSError: pass
            for path in self.cache_directory.glob("attempt_*.*"):
                try: path.unlink(missing_ok=True)
                except OSError: pass
            self._invalidate_cache_size_locked()
        self.event_queue.put(("attempts_cleared", len(attempts)))
        return len(attempts)

    def clear_unresolved(self) -> int:
        """Remove temporary attempts that still need an operator decision.

        Not-decided and Review records are treated as unresolved. Exported and
        evidence files live outside the temporary cache and are never touched.
        """
        unresolved = {AttemptDecision.NOT_DECIDED, AttemptDecision.REVIEW}
        return self._clear_matching(lambda attempt: attempt.decision in unresolved)

    def _clear_matching(self, predicate) -> int:
        with self._lock:
            targets = [attempt for attempt in self._attempts if not attempt.persistent and predicate(attempt)]
            if not targets:
                return 0
            target_ids = {attempt.attempt_id for attempt in targets}
            self._cancelled_attempt_ids.update(target_ids)
            for attempt_id in target_ids:
                self._pending_exports.pop(attempt_id, None)
                cap = self._video_caps.pop(attempt_id, None)
                if cap is not None:
                    cap.release()
                self._frame_cache.pop(attempt_id, None)
                self._video_next_index.pop(attempt_id, None)
            self._attempts = [attempt for attempt in self._attempts if attempt.attempt_id not in target_ids]
            for attempt in targets:
                for path in (attempt.temp_video_path, attempt.temp_metadata_path):
                    if path:
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            pass
            self._invalidate_cache_size_locked()
        self.event_queue.put(("attempts_cleared", len(targets)))
        return len(targets)

    def request_export(self, attempt_id: int, output_directory: Path) -> bool:
        output_directory.mkdir(parents=True, exist_ok=True)
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None:
                return False
            if attempt.state in {AttemptState.COLLECTING, AttemptState.ENCODING}:
                self._pending_exports[attempt_id] = output_directory
                self.event_queue.put(("message", f"Attempt #{attempt_id:02d} will export after post-roll is complete."))
                self.event_queue.put(("attempt_export_progress", (attempt_id, 0, None)))
                return True
            if not attempt.temp_video_path or not attempt.temp_video_path.exists():
                return False
            attempt.state = AttemptState.EXPORTING
            source = attempt.temp_video_path
            meta_source = attempt.temp_metadata_path
            source_size = source.stat().st_size
            created = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(attempt.created_wall_time))
            destination = output_directory / f"attempt_{attempt_id:02d}_{created}{source.suffix}"
            meta_destination = destination.with_suffix(".json")
        name = f"attempt-export-{attempt_id}"
        self.event_queue.put(("attempt_export_progress", (attempt_id, 0, source_size)))
        worker = Thread(target=self._copy_export, args=(attempt_id, source, destination, meta_source, meta_destination), name=name, daemon=True)
        with self._lock:
            self._workers[name] = worker
        worker.start()
        return True

    def delete(self, attempt_id: int, force: bool = False) -> bool:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if (
                attempt is None
                or (attempt.selected and not force)
                or attempt.protected
                or attempt.state in {AttemptState.COLLECTING, AttemptState.ENCODING, AttemptState.EXPORTING}
            ):
                return False
            self._delete_locked(attempt)
        self.event_queue.put(("attempt_deleted", attempt_id))
        return True

    def frame_count(self, attempt_id: int) -> int:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            return attempt.frame_count if attempt else 0

    def get_frame(self, attempt_id: int, frame_index: int) -> MediaFrame:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None or attempt.frame_count <= 0:
                return MediaFrame(None, 0, 0, 0, 0.0)
            index = max(0, min(attempt.frame_count - 1, frame_index))
            cached = self._frame_cache.setdefault(attempt_id, OrderedDict())
            if index in cached:
                frame, timestamp = cached.pop(index)
                cached[index] = (frame, timestamp)
                return MediaFrame(frame, timestamp, index, attempt.frame_count, attempt.fps)
            if attempt.packets and index < len(attempt.packets):
                packet = attempt.packets[index]
                frame = decode_packet(packet)
                cached[index] = (frame, packet.timestamp_ns)
                while len(cached) > self.DECODE_CACHE_FRAMES:
                    cached.popitem(last=False)
                return MediaFrame(frame, packet.timestamp_ns, index, attempt.frame_count, attempt.fps)
            path = attempt.temp_video_path
            if not path or not path.exists():
                return MediaFrame(None, 0, index, attempt.frame_count, attempt.fps)
            cap = self._video_caps.get(attempt_id)
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(str(path))
                self._video_caps[attempt_id] = cap
            if self._video_next_index.get(attempt_id) != index:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = cap.read()
            if not ok:
                return MediaFrame(None, 0, index, attempt.frame_count, attempt.fps)
            timestamp = attempt.start_timestamp_ns + int(index / max(1.0, attempt.fps) * 1e9)
            cached[index] = (frame, timestamp)
            while len(cached) > self.DECODE_CACHE_FRAMES:
                cached.popitem(last=False)
            self._video_next_index[attempt_id] = index + 1
            return MediaFrame(frame, timestamp, index, attempt.frame_count, attempt.fps)

    def frame_index_at_timestamp(self, attempt_id: int, timestamp_ns: int) -> int:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None or attempt.frame_count <= 0:
                return 0
            if attempt.packets:
                # Binary search is unnecessary at <= 5000 packets and avoids a dependency.
                return min(range(len(attempt.packets)), key=lambda i: abs(attempt.packets[i].timestamp_ns - timestamp_ns))
            index = round((timestamp_ns - attempt.start_timestamp_ns) / 1e9 * max(1.0, attempt.fps))
            return max(0, min(attempt.frame_count - 1, index))

    def cache_size_bytes(self) -> int:
        now = time.monotonic()
        with self._lock:
            if self._cache_size_value is not None and now - self._cache_size_checked_at < self.CACHE_SIZE_CACHE_SECONDS:
                return self._cache_size_value
            total = 0
            for path in self.cache_directory.glob("attempt_*.*"):
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
            self._cache_size_value = total
            self._cache_size_checked_at = now
            return total

    def _loop(self) -> None:
        while not self._stop.wait(.05):
            self._collect_post_roll()
            self._cleanup()

    def _collect_post_roll(self) -> None:
        newest = self.ring_buffer.newest()
        now_monotonic_ns = time.monotonic_ns()
        to_encode: list[int] = []
        with self._lock:
            collecting = [a for a in self._attempts if a.state is AttemptState.COLLECTING]
            for attempt in collecting:
                target_end = attempt.freeze_timestamp_ns + int(attempt.post_seconds * 1e9)
                last_ns = attempt.packets[-1].timestamp_ns if attempt.packets else attempt.freeze_timestamp_ns
                if newest is not None:
                    end_ns = min(target_end, newest.timestamp_ns)
                    if end_ns > last_ns:
                        new_packets = self.ring_buffer.snapshot_between(last_ns + 1, end_ns)
                        if new_packets:
                            attempt.packets.extend(new_packets)
                            attempt.frame_count = len(attempt.packets)
                            attempt.fps = estimate_fps(attempt.packets, fallback=attempt.fps)
                            attempt.media_end_timestamp_ns = attempt.packets[-1].timestamp_ns
                stalled = now_monotonic_ns >= attempt.created_monotonic_ns + int((attempt.post_seconds + self.POST_ROLL_STALL_GRACE_SECONDS) * 1e9)
                complete = newest is not None and newest.timestamp_ns >= target_end
                if complete or stalled:
                    if stalled and not complete:
                        warning = "Post-roll ended early because live capture stopped advancing."
                        attempt.quality_warning = f"{attempt.quality_warning}; {warning}" if attempt.quality_warning else warning
                    attempt.state = AttemptState.ENCODING
                    to_encode.append(attempt.attempt_id)
                    self.event_queue.put(("attempt_updated", attempt.attempt_id))
        for attempt_id in to_encode:
            self._submit_encode(attempt_id)

    def _submit_encode(self, attempt_id: int) -> None:
        with self._lock:
            attempt = self._find_locked(attempt_id)
            if attempt is None or f"attempt-encode-{attempt_id}" in self._workers:
                return
            packets = list(attempt.packets)
        name = f"attempt-encode-{attempt_id}"
        worker = Thread(target=self._encode_attempt, args=(attempt_id, packets), name=name, daemon=True)
        with self._lock:
            self._workers[name] = worker
        worker.start()

    def _encode_attempt(self, attempt_id: int, packets: list[FramePacket]) -> None:
        staging_directory: Path | None = None
        try:
            with self._lock:
                attempt = self._find_locked(attempt_id)
                persistent = bool(attempt and attempt.persistent)
            output_directory = self.persistent_directory if persistent else self.cache_directory
            base_name = f"recording_{attempt_id:04d}" if persistent else f"attempt_{attempt_id:04d}"
            if persistent:
                # Encode away from the visible library. A crash or cancelled
                # worker can therefore leave no half-written recording item.
                staging_directory = self.persistent_directory / ".incomplete"
                staging_directory.mkdir(parents=True, exist_ok=True)
                output_directory = staging_directory
            result = export_clip(
                packets,
                output_directory,
                preferred_codec=self.config.temp_codec,
                write_sidecar_json=False,
                base_name=base_name,
            )
            if persistent:
                final_video = self.persistent_directory / result.video_path.name
                result.video_path.replace(final_video)
                result = replace(result, video_path=final_video)
            with self._lock:
                attempt = self._find_locked(attempt_id)
                if attempt is None or attempt_id in self._cancelled_attempt_ids:
                    self._cancelled_attempt_ids.discard(attempt_id)
                    result.video_path.unlink(missing_ok=True)
                    if result.sidecar_path: result.sidecar_path.unlink(missing_ok=True)
                    return
                attempt.temp_video_path = result.video_path
                attempt.temp_metadata_path = None
                attempt.frame_count = result.frame_count
                attempt.fps = result.fps
                attempt.state = AttemptState.READY
                attempt.media_start_timestamp_ns = packets[0].timestamp_ns
                attempt.media_end_timestamp_ns = packets[-1].timestamp_ns
                attempt.packets.clear()  # the durable MP4 now owns the large payload
                self._write_metadata_locked(attempt)
                pending = self._pending_exports.pop(attempt_id, None)
            self.event_queue.put(("attempt_ready", attempt_id))
            if pending:
                self.request_export(attempt_id, pending)
        except Exception as exc:
            with self._lock:
                attempt = self._find_locked(attempt_id)
                if attempt:
                    attempt.state, attempt.error = AttemptState.ERROR, str(exc)
            self.event_queue.put(("attempt_error", (attempt_id, str(exc))))
        finally:
            if staging_directory is not None:
                try:
                    for path in staging_directory.glob("recording_*.*"):
                        if path.is_file():
                            path.unlink(missing_ok=True)
                except OSError:
                    pass
            with self._lock:
                self._workers.pop(f"attempt-encode-{attempt_id}", None)

    def _copy_export(self, attempt_id: int, source: Path, destination: Path, meta_source: Path | None, meta_destination: Path) -> None:
        video_temp = destination.with_suffix(destination.suffix + ".tmp")
        metadata_temp = meta_destination.with_suffix(meta_destination.suffix + ".tmp")
        installed_video = False
        installed_metadata = False
        attempt: AttemptSession | None = None
        try:
            total_bytes = source.stat().st_size
            copied_bytes = 0
            with source.open("rb") as source_file, video_temp.open("wb") as destination_file:
                while True:
                    chunk = source_file.read(1024 * 1024)
                    if not chunk:
                        break
                    destination_file.write(chunk)
                    copied_bytes += len(chunk)
                    self.event_queue.put(("attempt_export_progress", (attempt_id, copied_bytes, total_bytes)))
            shutil.copystat(source, video_temp)
            video_temp.replace(destination)
            installed_video = True
            if meta_source and meta_source.exists():
                shutil.copy2(meta_source, metadata_temp)
                metadata_temp.replace(meta_destination)
                installed_metadata = True
            with self._lock:
                attempt = self._find_locked(attempt_id)
                if attempt is None or attempt_id in self._cancelled_attempt_ids:
                    self._cancelled_attempt_ids.discard(attempt_id)
                    raise RuntimeError("Attempt was removed while export was running")
                attempt.state = AttemptState.EXPORTED
                attempt.export_path = destination
                self._write_metadata_locked(attempt)
            self.event_queue.put(("attempt_exported", (attempt_id, destination)))
        except Exception as exc:
            for path, installed in ((video_temp, False), (metadata_temp, False), (destination, installed_video), (meta_destination, installed_metadata)):
                if installed or path in (video_temp, metadata_temp):
                    try: path.unlink(missing_ok=True)
                    except OSError: pass
            with self._lock:
                attempt = self._find_locked(attempt_id)
                if attempt and attempt_id not in self._cancelled_attempt_ids:
                    attempt.state, attempt.error = AttemptState.ERROR, str(exc)
            if attempt is not None:
                self.event_queue.put(("attempt_error", (attempt_id, str(exc))))
        finally:
            for path in (video_temp, metadata_temp):
                try: path.unlink(missing_ok=True)
                except OSError: pass
            with self._lock:
                self._workers.pop(f"attempt-export-{attempt_id}", None)

    def _cleanup(self) -> None:
        now = time.time()
        with self._lock:
            expired = [a for a in self._attempts if not a.persistent and a.expires_at_wall_time <= now and not a.selected and not a.protected and a.state not in {AttemptState.COLLECTING, AttemptState.ENCODING, AttemptState.EXPORTING}]
            for attempt in expired:
                self._delete_locked(attempt)
                self.event_queue.put(("attempt_deleted", attempt.attempt_id))
            self._enforce_limits_locked()

    def _enforce_limits_locked(self) -> None:
        def removable() -> Iterable[AttemptSession]:
            return (a for a in self._attempts if not a.persistent and not a.selected and not a.protected and a.state not in {AttemptState.COLLECTING, AttemptState.ENCODING, AttemptState.EXPORTING})
        while len(self._attempts) > self.config.max_attempts:
            victim = next(iter(removable()), None)
            if victim is None: break
            self._delete_locked(victim)
        limit = int(self.config.max_cache_gb * 1024 ** 3)
        while self.cache_size_bytes() > limit:
            victim = next(iter(removable()), None)
            if victim is None: break
            self._delete_locked(victim)

    def _delete_locked(self, attempt: AttemptSession) -> None:
        cap = self._video_caps.pop(attempt.attempt_id, None)
        if cap: cap.release()
        self._frame_cache.pop(attempt.attempt_id, None)
        self._video_next_index.pop(attempt.attempt_id, None)
        for path in (attempt.temp_video_path, attempt.temp_metadata_path):
            if path:
                try: path.unlink(missing_ok=True)
                except OSError: pass
        if attempt in self._attempts:
            self._attempts.remove(attempt)
        self._invalidate_cache_size_locked()

    def _invalidate_cache_size_locked(self) -> None:
        self._cache_size_value = None
        self._cache_size_checked_at = 0.0

    def _find_locked(self, attempt_id: int) -> AttemptSession | None:
        return next((a for a in self._attempts if a.attempt_id == attempt_id), None)

    @staticmethod
    def _public_copy(attempt: AttemptSession) -> AttemptSession:
        copy = replace(attempt)
        copy.packets = []  # do not leak/copy megabytes into the GUI
        copy.markers = list(attempt.markers)
        return copy

    def _write_metadata_locked(self, attempt: AttemptSession) -> None:
        directory = self.persistent_directory if attempt.persistent else self.cache_directory
        path = directory / (f"recording_{attempt.attempt_id:04d}.session.json" if attempt.persistent else f"attempt_{attempt.attempt_id:04d}.session.json")
        data = {
            "attempt_id": attempt.attempt_id,
            "created_wall_time": attempt.created_wall_time,
            "freeze_timestamp_ns": attempt.freeze_timestamp_ns,
            "pre_seconds": attempt.pre_seconds,
            "post_seconds": attempt.post_seconds,
            "expires_at_wall_time": attempt.expires_at_wall_time,
            "state": attempt.state.value,
            "persistent": attempt.persistent,
            "decision": attempt.decision.value,
            "decision_wall_time": attempt.decision_wall_time,
            "competitor_group": attempt.competitor_group,
            "competitor_number": attempt.competitor_number,
            "competitor_attempt_number": attempt.competitor_attempt_number,
            "competition_phase": attempt.competition_phase,
            "rotation_completed": attempt.rotation_completed,
            "counts_for_rotation": attempt.counts_for_rotation,
            "quality_warning": attempt.quality_warning,
            "adjudication_record_id": attempt.adjudication_record_id,
            "video": attempt.temp_video_path.name if attempt.temp_video_path else None,
            "fps": attempt.fps,
            "frame_count": attempt.frame_count,
            "freeze_frame_index": attempt.freeze_frame_index,
            "thumbnail_frame_index": attempt.thumbnail_frame_index,
            "takeoff_candidate_index": attempt.takeoff_candidate_index,
            "takeoff_confidence": attempt.takeoff_confidence,
            "takeoff_analysis_start_ns": attempt.takeoff_analysis_start_ns,
            "takeoff_analysis_end_ns": attempt.takeoff_analysis_end_ns,
            "automatic_advisory": attempt.automatic_advisory,
            "automatic_advisory_confidence": attempt.automatic_advisory_confidence,
            "automatic_advisory_frame_index": attempt.automatic_advisory_frame_index,
            "automatic_signed_clearance_cm": attempt.automatic_signed_clearance_cm,
            "automatic_uncertainty_cm": attempt.automatic_uncertainty_cm,
            "automatic_advisory_reason": attempt.automatic_advisory_reason,
            "automatic_advisory_engine": attempt.automatic_advisory_engine,
            "automatic_analysis_ms": attempt.automatic_analysis_ms,
            "width": attempt.width,
            "height": attempt.height,
            "media_start_timestamp_ns": attempt.media_start_timestamp_ns,
            "media_end_timestamp_ns": attempt.media_end_timestamp_ns,
            "media_start_wall_time_ns": attempt.media_start_wall_time_ns,
            "export_path": str(attempt.export_path) if attempt.export_path else None,
            "evidence_raw_path": str(attempt.evidence_raw_path) if attempt.evidence_raw_path else None,
            "evidence_annotated_path": str(attempt.evidence_annotated_path) if attempt.evidence_annotated_path else None,
            "markers": [{"timestamp_ns": m.timestamp_ns, "label": m.label} for m in attempt.markers],
        }
        temp_path = path.with_suffix(path.suffix + ".tmp")
        try:
            temp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(path)
            attempt.temp_metadata_path = path
            self._invalidate_cache_size_locked()
        except OSError:
            try: temp_path.unlink(missing_ok=True)
            except OSError: pass

    def _recover_cache_index(self) -> None:
        # Sessions from a previous crash remain useful until their recorded expiry.
        now = time.time()
        # The recordings directory belonged to the removed explicit Capture
        # Mode. Its files are migrated to exports by MainWindow and must not be
        # mixed back into the rolling-buffer attempt list.
        sources = [(self.cache_directory, False)]
        for directory, persistent in sources:
            directory.mkdir(parents=True, exist_ok=True)
            for path in sorted(directory.glob("*.session.json")):
                self._recover_session(path, directory, persistent, now)

    def _recover_session(self, path: Path, directory: Path, persistent: bool, now: float) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            expires = float(data.get("expires_at_wall_time", 0))
            if not persistent and expires <= now:
                path.unlink(missing_ok=True)
                video_name = data.get("video")
                if video_name:
                    (directory / video_name).unlink(missing_ok=True)
                return
            video_name = data.get("video")
            video_path = directory / video_name if video_name else None
            if not video_path or not video_path.exists():
                # A persistent session file with no finished media is an
                # interrupted recording marker, not a playable library item.
                # Remove only that orphan marker; never touch unrelated files.
                if persistent:
                    path.unlink(missing_ok=True)
                return
            attempt = AttemptSession(
                attempt_id=int(data["attempt_id"]),
                created_monotonic_ns=0,
                created_wall_time=float(data["created_wall_time"]),
                freeze_timestamp_ns=int(data["freeze_timestamp_ns"]),
                pre_seconds=float(data["pre_seconds"]),
                post_seconds=float(data["post_seconds"]),
                expires_at_wall_time=expires,
                state=AttemptState.READY,
                decision=AttemptDecision(data.get("decision", "Not decided").replace("Pending", "Not decided")),
                decision_wall_time=float(data.get("decision_wall_time", 0.0)),
                competitor_group=str(data.get("competitor_group", "")),
                competitor_number=int(data.get("competitor_number", 0)),
                competitor_attempt_number=int(data.get("competitor_attempt_number", 0)),
                competition_phase=str(data.get("competition_phase", "qualification")),
                persistent=bool(data.get("persistent", persistent)),
                rotation_completed=bool(data.get("rotation_completed", False)),
                counts_for_rotation=bool(data.get("counts_for_rotation", True)),
                quality_warning=str(data.get("quality_warning", "")),
                adjudication_record_id=str(data.get("adjudication_record_id", "")),
                temp_video_path=video_path,
                temp_metadata_path=path,
                fps=float(data["fps"]),
                frame_count=int(data["frame_count"]),
                freeze_frame_index=int(data["freeze_frame_index"]),
                thumbnail_frame_index=(
                    int(data["thumbnail_frame_index"])
                    if data.get("thumbnail_frame_index") is not None
                    else None
                ),
                takeoff_candidate_index=data.get("takeoff_candidate_index"),
                takeoff_confidence=float(data.get("takeoff_confidence", 0.0)),
                takeoff_analysis_start_ns=int(data["takeoff_analysis_start_ns"]) if data.get("takeoff_analysis_start_ns") is not None else None,
                takeoff_analysis_end_ns=int(data["takeoff_analysis_end_ns"]) if data.get("takeoff_analysis_end_ns") is not None else None,
                automatic_advisory=str(data.get("automatic_advisory", "")),
                automatic_advisory_confidence=float(data.get("automatic_advisory_confidence", 0.0)),
                automatic_advisory_frame_index=(int(data["automatic_advisory_frame_index"]) if data.get("automatic_advisory_frame_index") is not None else None),
                automatic_signed_clearance_cm=(float(data["automatic_signed_clearance_cm"]) if data.get("automatic_signed_clearance_cm") is not None else None),
                automatic_uncertainty_cm=(float(data["automatic_uncertainty_cm"]) if data.get("automatic_uncertainty_cm") is not None else None),
                automatic_advisory_reason=str(data.get("automatic_advisory_reason", "")),
                automatic_advisory_engine=str(data.get("automatic_advisory_engine", "")),
                automatic_analysis_ms=float(data.get("automatic_analysis_ms", 0.0)),
                width=int(data.get("width", 0)),
                height=int(data.get("height", 0)),
                media_start_timestamp_ns=int(data.get("media_start_timestamp_ns", 0)),
                media_end_timestamp_ns=int(data.get("media_end_timestamp_ns", 0)),
                media_start_wall_time_ns=int(data.get("media_start_wall_time_ns", 0)),
                markers=[AttemptMarker(int(m["timestamp_ns"]), str(m.get("label", "Marker"))) for m in data.get("markers", [])],
                export_path=Path(data["export_path"]) if data.get("export_path") else None,
                evidence_raw_path=Path(data["evidence_raw_path"]) if data.get("evidence_raw_path") else None,
                evidence_annotated_path=Path(data["evidence_annotated_path"]) if data.get("evidence_annotated_path") else None,
            )
            self._attempts.append(attempt)
            self._next_id = max(self._next_id, attempt.attempt_id + 1)
        except Exception:
            return
