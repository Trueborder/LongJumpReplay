from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time

import cv2

from .background_tasks import TaskContext


MIGRATION_SCHEMA = 1


@dataclass(frozen=True, slots=True)
class MigratedRecording:
    source: str
    destination: str
    sha256: str
    recovered: bool = False


@dataclass(frozen=True, slots=True)
class MigrationReport:
    migrated: tuple[MigratedRecording, ...]
    quarantined: tuple[str, ...]
    backup_directory: str


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_video(path: Path) -> tuple[bool, int]:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return False, 0
        frames = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        ok_first, first = cap.read()
        if not ok_first or first is None:
            return False, frames
        if frames > 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, frames - 1))
            ok_last, last = cap.read()
            if not ok_last or last is None:
                return False, frames
        return True, frames
    finally:
        cap.release()


def _unique_destination(directory: Path, name: str) -> Path:
    candidate = directory / name
    for index in range(1, 10000):
        if not candidate.exists() and not candidate.with_suffix(candidate.suffix + ".partial").exists():
            return candidate
        stem = Path(name).stem
        suffix = Path(name).suffix
        candidate = directory / f"{stem}_{index:02d}{suffix}"
    raise RuntimeError(f"Could not create a unique export name for {name}")


def migrate_legacy_recordings(recordings: Path, exports: Path, context: TaskContext) -> MigrationReport:
    """Copy, validate and then archive recordings created by removed Capture Mode."""
    recordings = Path(recordings)
    exports = Path(exports)
    if not recordings.exists():
        return MigrationReport((), (), "")

    complete_videos = sorted(path for path in recordings.glob("recording_*.*") if path.suffix.lower() in {".mp4", ".avi"})
    incomplete_dir = recordings / ".incomplete"
    incomplete_videos = sorted(
        path for path in incomplete_dir.glob("recording_*.*")
        if path.is_file() and path.suffix.lower() in {".mp4", ".avi"}
    ) if incomplete_dir.exists() else []
    videos = [(path, False) for path in complete_videos] + [(path, True) for path in incomplete_videos]
    if not videos:
        return MigrationReport((), (), "")

    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    destination_dir = exports / "legacy-recordings" / time.strftime("%Y-%m-%d")
    backup_dir = recordings / ".migrated-backup" / stamp
    quarantine_dir = recordings / ".migration-quarantine" / stamp
    destination_dir.mkdir(parents=True, exist_ok=True)

    migrated: list[MigratedRecording] = []
    quarantined: list[str] = []
    total = len(videos)
    for number, (source, recovered) in enumerate(videos, 1):
        context.report(number - 1, total, source.name)
        context.check_cancelled()
        valid, frame_count = _validate_video(source)
        if not valid:
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            target = _unique_destination(quarantine_dir, source.name)
            shutil.move(str(source), str(target))
            quarantined.append(str(target))
            continue

        prefix = "recovered_" if recovered else ""
        destination = _unique_destination(destination_dir, f"{prefix}{source.name}")
        partial = destination.with_suffix(destination.suffix + ".partial")
        shutil.copy2(source, partial)
        if partial.stat().st_size != source.stat().st_size or _hash(partial) != _hash(source):
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"Verification failed while migrating {source.name}")
        copied_valid, copied_frames = _validate_video(partial)
        if not copied_valid or copied_frames != frame_count:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"The migrated copy of {source.name} is not readable")
        partial.replace(destination)

        sidecar = source.with_suffix(".session.json")
        if not sidecar.exists():
            sidecar = source.with_suffix(".json")
        if sidecar.exists():
            metadata_target = destination.with_suffix(".json")
            metadata_partial = metadata_target.with_suffix(".json.partial")
            shutil.copy2(sidecar, metadata_partial)
            json.loads(metadata_partial.read_text(encoding="utf-8"))
            metadata_partial.replace(metadata_target)

        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(_unique_destination(backup_dir, source.name)))
        if sidecar.exists():
            shutil.move(str(sidecar), str(_unique_destination(backup_dir, sidecar.name)))
        migrated.append(MigratedRecording(str(source), str(destination), _hash(destination), recovered))
        context.report(number, total, destination.name)

    report = MigrationReport(tuple(migrated), tuple(quarantined), str(backup_dir) if backup_dir.exists() else "")
    manifest = destination_dir / f"migration-{stamp}.json"
    temporary = manifest.with_suffix(".json.partial")
    temporary.write_text(json.dumps({
        "schema_version": MIGRATION_SCHEMA,
        "completed_at": time.time(),
        "report": asdict(report),
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(manifest)
    return report
