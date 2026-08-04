from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
import subprocess


@dataclass(frozen=True, slots=True)
class CameraDevice:
    index: int
    name: str

    @property
    def label(self) -> str:
        return f"{self.index} · {self.name}"


def _parse_camera_names(output: str) -> list[str]:
    if not output.strip():
        return []
    try:
        decoded = json.loads(output)
    except json.JSONDecodeError:
        return []
    values = [decoded] if isinstance(decoded, str) else decoded if isinstance(decoded, list) else []
    names: list[str] = []
    for value in values:
        name = str(value).strip()
        if name and name not in names:
            names.append(name)
    return names


@lru_cache(maxsize=1)
def windows_camera_names() -> tuple[str, ...]:
    """Return friendly names registered in the Windows Camera/Image classes."""
    if os.name != "nt":
        return ()
    command = (
        "$devices = @(Get-CimInstance Win32_PnPEntity | "
        "Where-Object { $_.Status -eq 'OK' -and $_.PNPClass -in @('Camera','Image') }); "
        "@($devices | ForEach-Object { $_.Name }) | ConvertTo-Json -Compress"
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            creationflags=creation_flags,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if completed.returncode != 0:
        return ()
    return tuple(_parse_camera_names(completed.stdout))


def enumerate_camera_devices(current_index: int = 0) -> list[CameraDevice]:
    devices = [CameraDevice(index, name) for index, name in enumerate(windows_camera_names())]
    if not devices:
        return [CameraDevice(current_index, f"Camera {current_index} (configured)")]
    if current_index >= len(devices):
        devices.append(CameraDevice(current_index, f"Camera {current_index} (configured)"))
    return devices
