from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
from dataclasses import dataclass

APP_NAME = "LongJumpReplay"


@dataclass(frozen=True, slots=True)
class AppDataPaths:
    """Central user-data layout shared by the desktop application."""

    root: Path
    cache: Path
    recordings: Path
    exports: Path
    evidence: Path
    adjudication: Path
    thumbnails: Path
    validation_samples: Path
    sessions: Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def application_directory() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundled_resource(relative_path: str | Path) -> Path:
    base = Path(getattr(sys, "_MEIPASS", application_directory()))
    return base / Path(relative_path)


def local_app_data_directory() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    if raw:
        return Path(raw) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def writable_data_directory() -> Path:
    """Return a per-user writable location without requiring admin rights."""
    path = local_app_data_directory()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_default_config(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    embedded = bundled_resource("config.json")
    if embedded.exists():
        shutil.copyfile(embedded, destination)


def prepare_config_path(explicit_path: str | Path | None) -> Path:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    # Source builds keep config in the project. Portable EXE builds keep user
    # state in LocalAppData so the application works even from read-only media.
    if not is_frozen():
        return (application_directory() / "config.json").resolve()

    target = writable_data_directory() / "config.json"
    if not target.exists():
        _copy_default_config(target)
    return target.resolve()


def resolve_user_path(config_path: Path, value: str) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(value)))
    if expanded.is_absolute():
        return expanded.resolve()
    # Frozen builds store cache/exports in LocalAppData by default. This avoids
    # failures when the shared portable folder is under Program Files or OneDrive.
    base = writable_data_directory() if is_frozen() else config_path.parent
    return (base / expanded).resolve()


def app_data_paths(
    config_path: Path,
    *,
    cache_directory: str = "cache",
    recordings_directory: str = "recordings",
    export_directory: str = "exports",
    evidence_directory: str = "evidence",
) -> AppDataPaths:
    """Resolve mutable paths from one config/user-data root."""
    cache = resolve_user_path(config_path, cache_directory)
    recordings = resolve_user_path(config_path, recordings_directory)
    exports = resolve_user_path(config_path, export_directory)
    sessions = default_sessions_directory()
    return AppDataPaths(
        root=cache.parent,
        cache=cache,
        recordings=recordings,
        exports=exports,
        evidence=exports / evidence_directory,
        adjudication=cache.parent / "adjudication",
        thumbnails=recordings / ".thumbnails",
        validation_samples=cache.parent / "validation-samples",
        sessions=sessions,
    )


def default_sessions_directory() -> Path:
    """Return the operator-facing session root on the user desktop."""
    home = Path.home()
    for name in ("Desktop", "Plocha"):
        candidate = home / name
        if candidate.exists():
            return candidate / f"{APP_NAME} Sessions"
    return home / "Desktop" / f"{APP_NAME} Sessions"


def crash_log_path(config_path: Path) -> Path:
    return config_path.parent / "LongJumpReplay-crash.log"


def runtime_log_path(config_path: Path) -> Path:
    return config_path.parent / "LongJumpReplay-runtime.jsonl"
