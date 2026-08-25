"""Signed release discovery, download verification, and installer hand-off."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import __version__
from .licensing import _rsa_verify_with_key
from .portable_paths import writable_data_directory
from .update_public_key import UPDATE_PUBLIC_KEY_E, UPDATE_PUBLIC_KEY_N


UPDATE_MANIFEST_URL = os.environ.get(
    "LJR_UPDATE_MANIFEST_URL", "https://files.tomaspisar.cz/latest.json"
)
UPDATE_HOST = "files.tomaspisar.cz"
UPDATE_PRODUCT = "longjumpreplay"
UPDATE_CHANNEL = "stable"
UPDATE_TIMEOUT = 8
MAX_MANIFEST_BYTES = 128 * 1024
MAX_INSTALLER_BYTES = 512 * 1024 * 1024
STATE_FILENAME = "update-state.json"
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
SHA256_PATTERN = re.compile(r"^[0-9A-Fa-f]{64}$")


class UpdateError(Exception):
    """A release could not be trusted, downloaded, or launched."""


class UpdateCancelled(UpdateError):
    """The download was safely cancelled and its partial file removed."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    published_at: str
    installer_url: str
    sha256: str
    size: int
    notes: tuple[str, ...]


@dataclass(frozen=True)
class UpdateCheckResult:
    status: Literal["available", "current", "skipped", "error"]
    release: ReleaseInfo | None = None
    message: str = ""


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(value.strip())
    if not match:
        raise UpdateError(f"Invalid release version: {value!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _decode_signature(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as error:
        raise UpdateError("The update signature is not valid base64url.") from error


def verify_manifest(document: dict[str, Any], modulus: int | None = None) -> ReleaseInfo:
    if document.get("schema") != 1:
        raise UpdateError("The update manifest schema is not supported.")
    payload = document.get("payload")
    signature = document.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str) or not signature:
        raise UpdateError("The update manifest is incomplete.")

    public_modulus = UPDATE_PUBLIC_KEY_N if modulus is None else modulus
    if public_modulus is None:
        raise UpdateError("No production update key is embedded in this build.")
    if not _rsa_verify_with_key(
        canonical_payload(payload), _decode_signature(signature), public_modulus, UPDATE_PUBLIC_KEY_E
    ):
        raise UpdateError("The update manifest signature is invalid.")

    if payload.get("product") != UPDATE_PRODUCT or payload.get("channel") != UPDATE_CHANNEL:
        raise UpdateError("The update manifest is for a different product or channel.")

    version = str(payload.get("version") or "")
    parse_version(version)
    installer_url = str(payload.get("installer_url") or "")
    parsed = urlparse(installer_url)
    expected_name = f"LongJumpReplay-Setup-{version}.exe"
    if (
        parsed.scheme != "https"
        or parsed.hostname != UPDATE_HOST
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or parsed.path != f"/releases/{version}/{expected_name}"
    ):
        raise UpdateError("The update installer URL is not allowed.")

    digest = str(payload.get("sha256") or "").upper()
    if not SHA256_PATTERN.fullmatch(digest):
        raise UpdateError("The update checksum is invalid.")
    try:
        size = int(payload.get("size"))
    except (TypeError, ValueError) as error:
        raise UpdateError("The update size is invalid.") from error
    if size < 1 or size > MAX_INSTALLER_BYTES:
        raise UpdateError("The update size is outside the allowed range.")

    raw_notes = payload.get("notes")
    if not isinstance(raw_notes, list) or not all(isinstance(item, str) for item in raw_notes):
        raise UpdateError("The update release notes are invalid.")
    notes = tuple(item.strip() for item in raw_notes[:12] if item.strip())
    return ReleaseInfo(
        version=version,
        published_at=str(payload.get("published_at") or ""),
        installer_url=installer_url,
        sha256=digest,
        size=size,
        notes=notes,
    )


def update_state_path() -> Path:
    return writable_data_directory() / STATE_FILENAME


def load_skipped_version(path: Path | None = None) -> str | None:
    target = path or update_state_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8")).get("skipped_version")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) and VERSION_PATTERN.fullmatch(value) else None


def skip_version(version: str, path: Path | None = None) -> None:
    parse_version(version)
    target = path or update_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps({"skipped_version": version}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def _read_manifest(opener: Callable[..., Any], manifest_url: str) -> dict[str, Any]:
    request = Request(
        manifest_url,
        headers={"Accept": "application/json", "User-Agent": f"LongJumpReplay/{__version__} updater"},
    )
    try:
        with opener(request, timeout=UPDATE_TIMEOUT) as response:
            raw = response.read(MAX_MANIFEST_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise UpdateError("The update service could not be reached.") from error
    if len(raw) > MAX_MANIFEST_BYTES:
        raise UpdateError("The update manifest is unexpectedly large.")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError("The update manifest is unreadable.") from error
    if not isinstance(document, dict):
        raise UpdateError("The update manifest is not a JSON object.")
    return document


def check_for_update(
    *,
    current_version: str = __version__,
    opener: Callable[..., Any] = urlopen,
    manifest_url: str = UPDATE_MANIFEST_URL,
    modulus: int | None = None,
    respect_skip: bool = True,
    state_path: Path | None = None,
) -> UpdateCheckResult:
    try:
        release = verify_manifest(_read_manifest(opener, manifest_url), modulus)
        if parse_version(release.version) <= parse_version(current_version):
            return UpdateCheckResult("current", release)
        if respect_skip and load_skipped_version(state_path) == release.version:
            return UpdateCheckResult("skipped", release)
        return UpdateCheckResult("available", release)
    except UpdateError as error:
        return UpdateCheckResult("error", message=str(error))


class UpdateCheckTask:
    """A single daemon-thread update check that the Tk thread can poll."""

    def __init__(self, *, respect_skip: bool = True) -> None:
        self._results: queue.Queue[UpdateCheckResult] = queue.Queue(maxsize=1)
        self._result: UpdateCheckResult | None = None
        self._thread = threading.Thread(
            target=self._run, args=(respect_skip,), name="update-check", daemon=True
        )

    def _run(self, respect_skip: bool) -> None:
        self._results.put(check_for_update(respect_skip=respect_skip))

    def start(self) -> "UpdateCheckTask":
        self._thread.start()
        return self

    @property
    def done(self) -> bool:
        return self._result is not None or not self._thread.is_alive()

    def result(self) -> UpdateCheckResult | None:
        if self._result is None:
            try:
                self._result = self._results.get_nowait()
            except queue.Empty:
                return None
        return self._result


def start_update_check(*, respect_skip: bool = True) -> UpdateCheckTask:
    return UpdateCheckTask(respect_skip=respect_skip).start()


def installer_directory() -> Path:
    return writable_data_directory() / "updates"


def download_update(
    release: ReleaseInfo,
    *,
    opener: Callable[..., Any] = urlopen,
    destination_directory: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
    status: Callable[[Literal["downloading", "verifying", "preparing"]], None] | None = None,
) -> Path:
    directory = destination_directory or installer_directory()
    directory.mkdir(parents=True, exist_ok=True)
    filename = Path(urlparse(release.installer_url).path).name
    destination = directory / filename
    partial = destination.with_suffix(destination.suffix + ".partial")
    partial.unlink(missing_ok=True)
    request = Request(
        release.installer_url,
        headers={"Accept": "application/octet-stream", "User-Agent": f"LongJumpReplay/{__version__} updater"},
    )
    digest = hashlib.sha256()
    received = 0
    try:
        if status:
            status("downloading")
        with opener(request, timeout=UPDATE_TIMEOUT) as response, partial.open("wb") as output:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise UpdateCancelled("The update download was cancelled safely.")
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                received += len(chunk)
                if received > release.size or received > MAX_INSTALLER_BYTES:
                    raise UpdateError("The downloaded installer is larger than expected.")
                digest.update(chunk)
                output.write(chunk)
                if progress:
                    progress(received, release.size)
        if cancel_event is not None and cancel_event.is_set():
            raise UpdateCancelled("The update download was cancelled safely.")
        if status:
            status("verifying")
        if received != release.size:
            raise UpdateError("The downloaded installer size does not match the manifest.")
        if digest.hexdigest().upper() != release.sha256:
            raise UpdateError("The downloaded installer checksum does not match the signed manifest.")
        if status:
            status("preparing")
        partial.replace(destination)
        return destination
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        partial.unlink(missing_ok=True)
        raise UpdateError("The installer download failed.") from error


def schedule_installer_after_exit(installer: Path) -> None:
    """Confirm that Windows started Inno Setup before the application exits.

    Inno Setup receives ``/FORCECLOSEAPPLICATIONS`` and therefore owns the
    final hand-off from the still-running application. Waiting for our own PID
    before launching Setup is unsafe: a stuck shutdown worker can leave the
    window gone while preventing the installer from ever starting.
    """
    resolved = installer.resolve()
    if not resolved.is_file() or resolved.suffix.lower() != ".exe":
        raise UpdateError("The verified installer file is missing.")
    escaped = str(resolved).replace("'", "''")
    install_log = installer_directory() / "update-install.log"
    escaped_arguments = (
        "/SP- /SILENT /NORESTART /FORCECLOSEAPPLICATIONS "
        f'/LOG="{install_log}"'
    ).replace("'", "''")
    command = (
        "$ErrorActionPreference = 'Stop'; "
        f"$installer = Start-Process -FilePath '{escaped}' "
        f"-ArgumentList '{escaped_arguments}' -PassThru; "
        "if ($null -eq $installer) { throw 'Windows did not start the installer.' }"
    )
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                "-EncodedCommand", encoded,
            ],
            close_fds=True,
            creationflags=creation_flags,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise UpdateError("The update installer could not be scheduled.") from error
    if result.returncode != 0:
        raise UpdateError(
            f"Windows did not start the update installer. Try again, or run it manually from:\n{resolved}"
        )
