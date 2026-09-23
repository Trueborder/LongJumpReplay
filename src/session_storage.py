from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
import time
from typing import Any, Iterable
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    metadata: bool = True
    recordings: bool = True
    exports: bool = True
    frames: bool = True
    diagnostics: bool = False
    temporary: bool = False


@dataclass(frozen=True, slots=True)
class SessionPaths:
    root: Path
    recordings: Path
    exports: Path
    evidence: Path
    frames: Path
    thumbnails: Path
    diagnostics: Path
    incomplete: Path


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in " ._-" else "_" for char in value).strip(" .")
    return cleaned[:70] or "Session"


class SessionStore:
    """Own one operator-facing session folder and its crash-safe manifest."""

    def __init__(self, parent: Path, label: str = "Session") -> None:
        self.parent = Path(parent)
        self.session_id = str(uuid4())
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
        root = self.parent / f"{_safe_name(label)}_{stamp}"
        suffix = 2
        while root.exists():
            root = self.parent / f"{_safe_name(label)}_{stamp}_{suffix}"
            suffix += 1
        self.paths = SessionPaths(
            root=root,
            recordings=root / "recordings",
            exports=root / "exports",
            evidence=root / "evidence",
            frames=root / "frames",
            thumbnails=root / "thumbnails",
            diagnostics=root / "diagnostics",
            incomplete=root / ".incomplete",
        )
        self.manifest_path = self.paths.root / "session.json"
        self._created_at = time.time()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        self.parent.mkdir(parents=True, exist_ok=True)
        self.paths.root.mkdir(parents=True, exist_ok=True)
        for path in asdict(self.paths).values():
            if path != self.paths.root:
                path.mkdir(parents=True, exist_ok=True)

    def write_manifest(self, *, competition: Any, attempts: Iterable[Any], roster: Iterable[Any], state: str = "open") -> Path:
        payload = {
            "schema_version": 1,
            "session_id": self.session_id,
            "created_at": self._created_at,
            "updated_at": time.time(),
            "state": state,
            "competition": _json_safe(asdict(competition) if hasattr(competition, "__dataclass_fields__") else competition),
            "roster": [_json_safe(asdict(item) if hasattr(item, "__dataclass_fields__") else item) for item in roster],
            "attempts": [self._attempt_summary(item) for item in attempts],
            "paths": {name: str(path) for name, path in asdict(self.paths).items()},
        }
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.manifest_path)
        return self.manifest_path

    @staticmethod
    def _attempt_summary(attempt: Any) -> dict[str, Any]:
        fields = (
            "attempt_id", "created_wall_time", "state", "decision", "competitor_group",
            "competitor_number", "competitor_attempt_number", "competition_phase",
            "persistent", "thumbnail_frame_index", "freeze_frame_index", "frame_count",
            "fps", "temp_video_path", "export_path", "evidence_raw_path", "evidence_annotated_path",
            "adjudication_record_id", "automatic_advisory", "quality_warning",
        )
        result: dict[str, Any] = {}
        for field in fields:
            value = getattr(attempt, field, None)
            result[field] = getattr(value, "value", value)
        return _json_safe(result)

    @property
    def created_at(self) -> float:
        return self._created_at

    def apply_retention(self, plan: RetentionPlan, *, external_recordings: Iterable[Path] = ()) -> list[Path]:
        """Move unretained session categories to recoverable local trash."""
        removed: list[Path] = []
        category_paths = (
            ("metadata", (self.manifest_path,)),
            ("recordings", (self.paths.recordings,)),
            ("exports", (self.paths.exports, self.paths.evidence)),
            ("frames", (self.paths.frames, self.paths.thumbnails)),
            ("diagnostics", (self.paths.diagnostics,)),
            ("temporary", (self.paths.incomplete,)),
        )
        for category, paths in category_paths:
            if getattr(plan, category):
                continue
            for path in paths:
                if not path.exists():
                    continue
                if path.is_dir() and not any(path.iterdir()):
                    continue
                self._move_to_recoverable_trash(path)
                removed.append(path)
        if not plan.recordings:
            internal = {path.resolve() for path in self.paths.recordings.rglob("*") if path.is_file()} if self.paths.recordings.exists() else set()
            for path in external_recordings:
                candidate = Path(path)
                if not candidate.exists() or candidate.resolve() in internal:
                    continue
                self._move_to_recoverable_trash(candidate)
                removed.append(candidate)
        return removed

    def _move_to_recoverable_trash(self, path: Path) -> None:
        trash = self.parent / ".LongJumpReplay-Trash"
        trash.mkdir(parents=True, exist_ok=True)
        target = trash / f"{self.session_id}_{path.name}_{int(time.time() * 1000)}"
        shutil.move(str(path), str(target))