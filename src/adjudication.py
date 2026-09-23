from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from threading import RLock
import time
from typing import Any, Iterable
from uuid import uuid4

from .models import AttemptSession


SCHEMA_VERSION = 1
JOURNAL_COMPACT_EVENTS = 24


class DurabilityError(RuntimeError):
    """Raised when an adjudication update cannot be written durably."""


@dataclass(slots=True)
class AthleteContext:
    athlete_id: str
    group: str = ""
    competitor_number: int = 0
    bib: str = ""
    name: str = ""
    club: str = ""
    category: str = ""
    start_order: int = 0
    external_id: str = ""


@dataclass(slots=True)
class BoardReferenceState:
    enabled: bool = False
    x_ratio: float = 0.0
    y_ratio: float = 0.0
    angle_deg: float = 0.0
    width_px: int = 1
    roi: list[float] = field(default_factory=list)


@dataclass(slots=True)
class EvidenceAssets:
    raw_path: str = ""
    annotated_path: str = ""
    metadata_path: str = ""
    clip_path: str = ""
    hashes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AdjudicationRecord:
    record_id: str
    media_attempt_id: int
    athlete: AthleteContext
    attempt_number: int
    competition_phase: str
    freeze_wall_time: float
    verdict: str = "Not decided"
    verdict_wall_time: float = 0.0
    decision_latency_seconds: float | None = None
    correction_count: int = 0
    distance_cm: int | None = None
    distance_source: str = ""
    wind_tenths: int | None = None
    wind_source: str = ""
    selected_frame_index: int | None = None
    selected_frame_timestamp_ns: int = 0
    camera_source: str = ""
    board_reference: BoardReferenceState = field(default_factory=BoardReferenceState)
    evidence: EvidenceAssets = field(default_factory=EvidenceAssets)
    quality_warning: str = ""
    media_available: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_distance_centimetres(value: str) -> int:
    text = str(value).strip()
    try:
        centimetres = int(text)
    except ValueError as exc:
        raise ValueError("Distance must be a whole number in centimetres") from exc
    if not 1 <= centimetres <= 1500:
        raise ValueError("Distance must be between 1 and 1500 cm")
    return centimetres


def parse_wind_metres_per_second(value: str) -> int | None:
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        wind = float(text)
    except ValueError as exc:
        raise ValueError("Wind must be a number in m/s") from exc
    tenths = round(wind * 10)
    if not -200 <= tenths <= 200 or abs(wind * 10 - tenths) > 1e-7:
        raise ValueError("Wind must be between -20.0 and +20.0 m/s with at most one decimal")
    return tenths


class AdjudicationSessionStore:
    """Crash-safe authoritative result storage independent of temporary media.

    Critical updates are appended and flushed before the in-memory state is
    changed. Periodic atomic snapshots keep startup bounded. A secondary
    journal can preserve updates if the main session directory becomes
    unavailable during an event.
    """

    def __init__(self, directory: Path, fallback_directory: Path | None = None) -> None:
        self.directory = Path(directory)
        self.fallback_directory = Path(fallback_directory) if fallback_directory else None
        self.snapshot_path = self.directory / "adjudication-session.json"
        self.backup_path = self.directory / "adjudication-session.json.bak"
        self.journal_path = self.directory / "adjudication-session.journal.jsonl"
        self.fallback_journal_path = (
            self.fallback_directory / "adjudication-recovery.journal.jsonl"
            if self.fallback_directory and self.fallback_directory.resolve() != self.directory.resolve()
            else None
        )
        self._lock = RLock()
        self.session_id = str(uuid4())
        self.created_at = time.time()
        self._records: dict[str, AdjudicationRecord] = {}
        self._roster: dict[str, AthleteContext] = {}
        self._applied_events: set[str] = set()
        self._journal_events = 0
        self.recovery_warnings: list[str] = []
        self._load()

    def records(self) -> list[AdjudicationRecord]:
        with self._lock:
            return [self._record_from_dict(self._record_to_dict(record)) for record in self._records.values()]

    def roster(self) -> list[AthleteContext]:
        with self._lock:
            return [AthleteContext(**asdict(item)) for item in self._roster.values()]

    def get(self, record_id: str) -> AdjudicationRecord | None:
        with self._lock:
            record = self._records.get(record_id)
            return self._record_from_dict(self._record_to_dict(record)) if record else None

    def get_for_attempt(self, attempt: AttemptSession) -> AdjudicationRecord | None:
        if attempt.adjudication_record_id:
            return self.get(attempt.adjudication_record_id)
        with self._lock:
            matches = [
                record for record in self._records.values()
                if record.media_attempt_id == attempt.attempt_id
                and abs(record.freeze_wall_time - attempt.created_wall_time) < 0.001
            ]
            if not matches:
                return None
            record = max(matches, key=lambda item: item.created_at)
            return self._record_from_dict(self._record_to_dict(record))

    def athlete_for(self, group: str, competitor_number: int) -> AthleteContext:
        key = self._athlete_key(group, competitor_number)
        with self._lock:
            existing = self._roster.get(key)
            if existing:
                return AthleteContext(**asdict(existing))
        return AthleteContext(
            athlete_id=key,
            group=group,
            competitor_number=competitor_number,
            bib=str(competitor_number) if competitor_number > 0 else "",
            category=group,
            start_order=competitor_number,
        )

    def replace_roster(self, athletes: Iterable[AthleteContext]) -> None:
        roster = {
            self._athlete_key(item.group or item.category, item.competitor_number): item
            for item in athletes
        }
        payload = {key: asdict(value) for key, value in roster.items()}
        self._commit_event("replace_roster", {"roster": payload})

    def replace_group_roster(self, group: str, athletes: Iterable[AthleteContext]) -> None:
        """Replace one group's editable start order without touching results."""
        group = str(group)
        with self._lock:
            if any(record.athlete.group == group or record.athlete.category == group for record in self._records.values()):
                raise ValueError("The order cannot be changed after attempts have been recorded for this group.")
            ordered: list[AthleteContext] = []
            for number, item in enumerate(athletes, start=1):
                copy = AthleteContext(**asdict(item))
                copy.group = group
                copy.category = copy.category or group
                copy.competitor_number = number
                copy.start_order = number
                copy.athlete_id = copy.external_id or copy.athlete_id or f"{group}:{number}"
                ordered.append(copy)
            roster = {key: value for key, value in self._roster.items() if key.split(":", 1)[0] != group}
            roster.update({self._athlete_key(group, item.competitor_number): item for item in ordered})
            payload = {key: asdict(value) for key, value in roster.items()}
        self._commit_event("replace_roster", {"roster": payload})
    def ensure_attempt(
        self,
        attempt: AttemptSession,
        *,
        athlete: AthleteContext | None = None,
        camera_source: str = "",
        board_reference: BoardReferenceState | None = None,
    ) -> AdjudicationRecord:
        with self._lock:
            if attempt.adjudication_record_id and attempt.adjudication_record_id in self._records:
                return self.get(attempt.adjudication_record_id)  # type: ignore[return-value]
            # The durable journal is intentionally written before the temporary
            # attempt metadata. A crash in that narrow window leaves the latter
            # without its record ID, so reattach by session-local media identity
            # and freeze time instead of creating a duplicate result.
            matches = [
                record for record in self._records.values()
                if record.media_attempt_id == attempt.attempt_id
                and abs(record.freeze_wall_time - attempt.created_wall_time) < 0.001
            ]
            if matches:
                record = max(matches, key=lambda item: item.created_at)
                return self._record_from_dict(self._record_to_dict(record))
        athlete = athlete or self.athlete_for(attempt.competitor_group, attempt.competitor_number)
        record = AdjudicationRecord(
            record_id=attempt.adjudication_record_id or str(uuid4()),
            media_attempt_id=attempt.attempt_id,
            athlete=athlete,
            attempt_number=attempt.competitor_attempt_number,
            competition_phase=attempt.competition_phase,
            freeze_wall_time=attempt.created_wall_time,
            verdict=attempt.decision.value,
            verdict_wall_time=attempt.decision_wall_time,
            camera_source=camera_source,
            board_reference=board_reference or BoardReferenceState(),
            quality_warning=attempt.quality_warning,
            media_available=bool(attempt.temp_video_path or attempt.packets or attempt.state.value in {"Collecting", "Encoding"}),
        )
        self._commit_event("upsert_record", {"record": self._record_to_dict(record)})
        return self.get(record.record_id)  # type: ignore[return-value]

    def record_verdict(
        self,
        record_id: str,
        verdict: str,
        *,
        frame_index: int | None,
        frame_timestamp_ns: int,
        board_reference: BoardReferenceState | None = None,
        now: float | None = None,
    ) -> AdjudicationRecord:
        with self._lock:
            current = self._records.get(record_id)
            if current is None:
                raise KeyError(record_id)
            updated = self._record_from_dict(self._record_to_dict(current))
        timestamp = time.time() if now is None else float(now)
        if current.verdict != verdict and current.verdict_wall_time:
            updated.correction_count += 1
        updated.verdict = verdict
        updated.verdict_wall_time = timestamp
        updated.decision_latency_seconds = max(0.0, timestamp - updated.freeze_wall_time)
        updated.selected_frame_index = frame_index
        updated.selected_frame_timestamp_ns = int(frame_timestamp_ns)
        if board_reference is not None:
            updated.board_reference = board_reference
        updated.updated_at = timestamp
        self._commit_event("upsert_record", {"record": self._record_to_dict(updated)})
        return self.get(record_id)  # type: ignore[return-value]

    def set_measurement(
        self,
        record_id: str,
        *,
        distance_cm: int | None,
        wind_tenths: int | None,
        source: str = "manual",
    ) -> AdjudicationRecord:
        if distance_cm is not None and not 1 <= int(distance_cm) <= 1500:
            raise ValueError("distance_cm must be between 1 and 1500")
        if wind_tenths is not None and not -200 <= int(wind_tenths) <= 200:
            raise ValueError("wind_tenths must be between -200 and 200")
        with self._lock:
            current = self._records.get(record_id)
            if current is None:
                raise KeyError(record_id)
            updated = self._record_from_dict(self._record_to_dict(current))
        updated.distance_cm = int(distance_cm) if distance_cm is not None else None
        updated.distance_source = source if distance_cm is not None else ""
        updated.wind_tenths = int(wind_tenths) if wind_tenths is not None else None
        updated.wind_source = source if wind_tenths is not None else ""
        updated.updated_at = time.time()
        self._commit_event("upsert_record", {"record": self._record_to_dict(updated)})
        return self.get(record_id)  # type: ignore[return-value]

    def set_evidence(
        self,
        record_id: str,
        *,
        raw_path: Path | None,
        annotated_path: Path | None,
        metadata_path: Path | None,
        clip_path: Path | None = None,
    ) -> AdjudicationRecord:
        with self._lock:
            current = self._records.get(record_id)
            if current is None:
                raise KeyError(record_id)
            updated = self._record_from_dict(self._record_to_dict(current))
        paths = {
            "raw": raw_path,
            "annotated": annotated_path,
            "metadata": metadata_path,
            "clip": clip_path,
        }
        updated.evidence = EvidenceAssets(
            raw_path=str(raw_path) if raw_path else "",
            annotated_path=str(annotated_path) if annotated_path else "",
            metadata_path=str(metadata_path) if metadata_path else "",
            clip_path=str(clip_path) if clip_path else "",
            hashes={name: file_sha256(path) for name, path in paths.items() if path and path.exists()},
        )
        updated.updated_at = time.time()
        self._commit_event("upsert_record", {"record": self._record_to_dict(updated)})
        return self.get(record_id)  # type: ignore[return-value]

    def mark_media_unavailable(self, record_id: str) -> None:
        with self._lock:
            current = self._records.get(record_id)
            if current is None or not current.media_available:
                return
            updated = self._record_from_dict(self._record_to_dict(current))
        updated.media_available = False
        updated.updated_at = time.time()
        self._commit_event("upsert_record", {"record": self._record_to_dict(updated)})

    def session_report(self) -> dict[str, Any]:
        records = self.records()
        decisions = [record for record in records if record.verdict != "Not decided"]
        latencies = sorted(record.decision_latency_seconds for record in decisions if record.decision_latency_seconds is not None)
        if not latencies:
            median = None
        elif len(latencies) % 2:
            median = latencies[len(latencies) // 2]
        else:
            midpoint = len(latencies) // 2
            median = (latencies[midpoint - 1] + latencies[midpoint]) / 2
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "duration_seconds": max(0.0, time.time() - self.created_at),
            "attempts_processed": len(records),
            "verdict_counts": {name: sum(record.verdict == name for record in records) for name in ("Valid", "Foul", "Review", "Not decided")},
            "operator_corrections": sum(record.correction_count for record in records),
            "median_decision_seconds": median,
            "lost_attempts": 0,
            "evidence_failures": sum(
                record.verdict in {"Valid", "Foul", "Review"} and not record.evidence.raw_path and not record.evidence.annotated_path
                for record in records
            ),
            "skipped_distance_entries": sum(record.verdict == "Valid" and record.distance_cm is None for record in records),
            "recovery_warnings": list(self.recovery_warnings),
        }

    def close(self) -> None:
        with self._lock:
            self._compact_locked()

    def _commit_event(self, kind: str, payload: dict[str, Any]) -> None:
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_id": str(uuid4()),
            "timestamp": time.time(),
            "kind": kind,
            "payload": payload,
        }
        canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        envelope = {"event": event, "sha256": sha256(canonical.encode("utf-8")).hexdigest()}
        line = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            try:
                self._append_durable(self.journal_path, line)
            except OSError as primary_error:
                if self.fallback_journal_path is None:
                    raise DurabilityError(f"Could not save adjudication update: {primary_error}") from primary_error
                try:
                    self._append_durable(self.fallback_journal_path, line)
                except OSError as fallback_error:
                    raise DurabilityError(
                        f"Could not save adjudication update to primary or recovery storage: {primary_error}; {fallback_error}"
                    ) from fallback_error
            self._apply_event(event)
            self._journal_events += 1
            if self._journal_events >= JOURNAL_COMPACT_EVENTS:
                try:
                    self._compact_locked()
                except OSError as exc:
                    self.recovery_warnings.append(f"Snapshot compaction failed: {exc}")

    @staticmethod
    def _append_durable(path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _apply_event(self, event: dict[str, Any]) -> None:
        event_id = str(event.get("event_id", ""))
        if not event_id or event_id in self._applied_events:
            return
        kind = event.get("kind")
        payload = event.get("payload", {})
        if kind == "upsert_record":
            record = self._record_from_dict(payload["record"])
            self._records[record.record_id] = record
        elif kind == "replace_roster":
            self._roster = {key: AthleteContext(**value) for key, value in payload.get("roster", {}).items()}
        self._applied_events.add(event_id)

    def _load(self) -> None:
        with self._lock:
            loaded = False
            for source in (self.snapshot_path, self.backup_path):
                if not source.exists():
                    continue
                try:
                    data = json.loads(source.read_text(encoding="utf-8"))
                    if int(data.get("schema_version", 0)) != SCHEMA_VERSION:
                        raise ValueError("unsupported schema")
                    self.session_id = str(data["session_id"])
                    self.created_at = float(data.get("created_at", time.time()))
                    self._records = {item["record_id"]: self._record_from_dict(item) for item in data.get("records", [])}
                    self._roster = {key: AthleteContext(**value) for key, value in data.get("roster", {}).items()}
                    loaded = True
                    if source == self.backup_path:
                        self.recovery_warnings.append("Recovered adjudication state from backup snapshot")
                    break
                except Exception as exc:
                    self.recovery_warnings.append(f"Ignored corrupt session snapshot {source.name}: {exc}")
            for journal in (self.journal_path, self.fallback_journal_path):
                if journal is None or not journal.exists():
                    continue
                self._load_journal(journal)
            if not loaded and self._records:
                self.recovery_warnings.append("Recovered adjudication state from journal")

    def _load_journal(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            self.recovery_warnings.append(f"Could not read recovery journal {path.name}: {exc}")
            return
        for index, line in enumerate(lines, start=1):
            try:
                envelope = json.loads(line)
                event = envelope["event"]
                canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                if envelope.get("sha256") != sha256(canonical.encode("utf-8")).hexdigest():
                    raise ValueError("checksum mismatch")
                self._apply_event(event)
                self._journal_events += 1
            except Exception as exc:
                self.recovery_warnings.append(f"Ignored invalid journal entry {path.name}:{index}: {exc}")

    def _compact_locked(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": time.time(),
            "records": [self._record_to_dict(record) for record in self._records.values()],
            "roster": {key: asdict(value) for key, value in self._roster.items()},
        }
        temporary = self.snapshot_path.with_suffix(self.snapshot_path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if self.snapshot_path.exists():
            shutil.copy2(self.snapshot_path, self.backup_path)
        temporary.replace(self.snapshot_path)
        empty = self.journal_path.with_suffix(self.journal_path.suffix + ".tmp")
        empty.write_text("", encoding="utf-8")
        empty.replace(self.journal_path)
        if self.fallback_journal_path and self.fallback_journal_path.exists():
            self.fallback_journal_path.write_text("", encoding="utf-8")
        self._applied_events.clear()
        self._journal_events = 0

    @staticmethod
    def _athlete_key(group: str, number: int) -> str:
        # Board navigation addresses an athlete by the current roster slot.
        # Stable external identity remains in AthleteContext.athlete_id and is
        # used by interchange adapters, not as the mutable board index.
        return f"{group or 'unassigned'}:{int(number)}"

    @staticmethod
    def _record_to_dict(record: AdjudicationRecord) -> dict[str, Any]:
        return asdict(record)

    @staticmethod
    def _record_from_dict(data: dict[str, Any]) -> AdjudicationRecord:
        values = dict(data)
        values["athlete"] = AthleteContext(**values.get("athlete", {"athlete_id": "unassigned:0"}))
        values["board_reference"] = BoardReferenceState(**values.get("board_reference", {}))
        values["evidence"] = EvidenceAssets(**values.get("evidence", {}))
        return AdjudicationRecord(**values)
