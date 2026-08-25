from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import threading

import pytest

from src.licensing import _encoded_message, _urlsafe_encode
from src.updater import (
    ReleaseInfo,
    UpdateCancelled,
    UpdateError,
    canonical_payload,
    check_for_update,
    download_update,
    load_skipped_version,
    parse_version,
    schedule_installer_after_exit,
    skip_version,
    verify_manifest,
)
from tools.generate_signing_key import generate_keypair


@pytest.fixture(scope="module")
def update_keypair():
    return generate_keypair(2048)


def manifest_for(update_keypair, version: str = "3.3.1", content: bytes = b"installer") -> dict:
    modulus, private_exponent = update_keypair
    payload = {
        "channel": "stable",
        "installer_url": f"https://files.tomaspisar.cz/releases/{version}/LongJumpReplay-Setup-{version}.exe",
        "notes": ["A safer update."],
        "product": "longjumpreplay",
        "published_at": "2026-08-19T12:00:00.000Z",
        "sha256": hashlib.sha256(content).hexdigest().upper(),
        "size": len(content),
        "version": version,
    }
    message = canonical_payload(payload)
    size = (modulus.bit_length() + 7) // 8
    encoded = _encoded_message(message, size)
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(size, "big")
    return {"schema": 1, "payload": payload, "signature": _urlsafe_encode(signature)}


class Response:
    def __init__(self, content: bytes):
        self.stream = io.BytesIO(content)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


def manifest_opener(document: dict):
    encoded = json.dumps(document).encode("utf-8")
    return lambda *_args, **_kwargs: Response(encoded)


def test_version_parser_is_strict():
    assert parse_version("3.3.0") == (3, 3, 0)
    for invalid in ("3.3", "v3.3.0", "03.3.0", "3.3.0-beta"):
        with pytest.raises(UpdateError):
            parse_version(invalid)


def test_signed_manifest_is_accepted(update_keypair):
    modulus, _ = update_keypair
    release = verify_manifest(manifest_for(update_keypair), modulus)
    assert release.version == "3.3.1"
    assert release.notes == ("A safer update.",)


def test_tampered_manifest_and_untrusted_url_are_rejected(update_keypair):
    modulus, _ = update_keypair
    tampered = manifest_for(update_keypair)
    tampered["payload"]["size"] += 1
    with pytest.raises(UpdateError, match="signature"):
        verify_manifest(tampered, modulus)

    wrong_url = manifest_for(update_keypair)
    wrong_url["payload"]["installer_url"] = "https://example.com/update.exe"
    # Re-sign so the URL allow-list, rather than the signature, is exercised.
    _, private_exponent = update_keypair
    message = canonical_payload(wrong_url["payload"])
    size = (modulus.bit_length() + 7) // 8
    encoded = _encoded_message(message, size)
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(size, "big")
    wrong_url["signature"] = _urlsafe_encode(signature)
    with pytest.raises(UpdateError, match="URL"):
        verify_manifest(wrong_url, modulus)


def test_current_available_and_skipped_results(update_keypair, tmp_path):
    modulus, _ = update_keypair
    state = tmp_path / "update-state.json"
    document = manifest_for(update_keypair)
    available = check_for_update(
        current_version="3.3.0", opener=manifest_opener(document), modulus=modulus, state_path=state
    )
    assert available.status == "available"
    skip_version("3.3.1", state)
    assert load_skipped_version(state) == "3.3.1"
    skipped = check_for_update(
        current_version="3.3.0", opener=manifest_opener(document), modulus=modulus, state_path=state
    )
    assert skipped.status == "skipped"
    manual = check_for_update(
        current_version="3.3.0", opener=manifest_opener(document), modulus=modulus,
        state_path=state, respect_skip=False,
    )
    assert manual.status == "available"
    current = check_for_update(
        current_version="3.3.1", opener=manifest_opener(document), modulus=modulus, state_path=state
    )
    assert current.status == "current"


def test_download_is_atomic_and_checksum_verified(tmp_path):
    content = b"verified installer bytes"
    release = ReleaseInfo(
        version="3.3.1",
        published_at="2026-08-19T12:00:00Z",
        installer_url="https://files.tomaspisar.cz/releases/3.3.1/LongJumpReplay-Setup-3.3.1.exe",
        sha256=hashlib.sha256(content).hexdigest().upper(),
        size=len(content),
        notes=(),
    )
    progress = []
    result = download_update(
        release,
        opener=lambda *_args, **_kwargs: Response(content),
        destination_directory=tmp_path,
        progress=lambda received, total: progress.append((received, total)),
    )
    assert result.read_bytes() == content
    assert progress[-1] == (len(content), len(content))
    assert not list(tmp_path.glob("*.partial"))


def test_download_cancellation_removes_partial_file(tmp_path):
    content = b"x" * (1024 * 1024)
    release = ReleaseInfo(
        version="3.3.1",
        published_at="2026-08-19T12:00:00Z",
        installer_url="https://files.tomaspisar.cz/releases/3.3.1/LongJumpReplay-Setup-3.3.1.exe",
        sha256=hashlib.sha256(content).hexdigest().upper(),
        size=len(content),
        notes=(),
    )
    cancelled = threading.Event()

    def progress(_received, _total):
        cancelled.set()

    with pytest.raises(UpdateCancelled):
        download_update(
            release,
            opener=lambda *_args, **_kwargs: Response(content),
            destination_directory=tmp_path,
            progress=progress,
            cancel_event=cancelled,
        )
    assert not list(tmp_path.glob("*.partial"))

    corrupt = ReleaseInfo(**{**release.__dict__, "sha256": "0" * 64})
    with pytest.raises(UpdateError, match="checksum"):
        download_update(corrupt, opener=lambda *_args, **_kwargs: Response(content), destination_directory=tmp_path)
    assert not list(tmp_path.glob("*.partial"))


def test_installer_handoff_confirms_hidden_installer_launch(monkeypatch, tmp_path):
    installer = tmp_path / "LongJumpReplay-Setup-3.3.1.exe"
    installer.write_bytes(b"exe")
    calls = []
    monkeypatch.setattr(
        "src.updater.subprocess.run",
        lambda args, **kwargs: calls.append((args, kwargs)) or type("Result", (), {"returncode": 0})(),
    )
    schedule_installer_after_exit(installer)
    args, kwargs = calls[0]
    assert args[:5] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden"]
    assert "-EncodedCommand" in args
    assert kwargs["close_fds"] is True
    command = base64.b64decode(args[-1]).decode("utf-16le")
    assert "Wait-Process" not in command
    assert "Start-Process" in command
    assert "/FORCECLOSEAPPLICATIONS" in command
    assert "/LOG=" in command
    assert kwargs["timeout"] == 60


def test_installer_handoff_reports_rejected_launch(monkeypatch, tmp_path):
    installer = tmp_path / "LongJumpReplay-Setup-3.3.1.exe"
    installer.write_bytes(b"exe")
    monkeypatch.setattr(
        "src.updater.subprocess.run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 1})(),
    )

    with pytest.raises(UpdateError, match="run it manually"):
        schedule_installer_after_exit(installer)


def test_production_update_key_is_embedded():
    from src.update_public_key import UPDATE_PUBLIC_KEY_N

    assert UPDATE_PUBLIC_KEY_N is not None
    assert UPDATE_PUBLIC_KEY_N.bit_length() >= 3072
