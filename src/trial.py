"""Free 72-hour evaluation state and service client.

The application verifies signed trial tokens with only a public key. The
private trial key belongs to the separately deployed trial service and must
never be placed in this repository or customer installer.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .licensing import (
    PRODUCT_ID,
    _encoded_message,
    _rsa_verify_with_key,
    canonical_payload,
    machine_code,
)
from .portable_paths import writable_data_directory


TRIAL_DURATION_SECONDS = 72 * 60 * 60
TRIAL_EXPORT_LIMIT = 3
TRIAL_TOKEN_PREFIX = "LJRT1"
TRIAL_SERVICE_URL = os.environ.get(
    "LJR_TRIAL_SERVICE_URL", "https://api.tomaspisar.cz/longjumpreplay"
).rstrip("/")
TIME_API_URL = os.environ.get(
    "LJR_TRIAL_TIME_URL", "https://worldtimeapi.org/api/timezone/Etc/UTC"
)
TRIAL_STATE_FILENAME = "trial-state.json"
TRIAL_CONSUMED_FILENAME = "trial-consumed.json"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Separate trial key. The matching private key is supplied to the trial
# service through LONGJUMP_TRIAL_KEY_PATH and is deliberately not included.
TRIAL_PUBLIC_KEY_N = int(
    "66942647103203304962590205770878281963883856246423548246142059846535808267002415706429161432110517422850179501288546919507565125717042738272242701670438773233776087003694421824183275992323098828098552938745663164729708471233261879684395171987966095298358923580400333948666291099382642414255448395815043429917"
)
TRIAL_PUBLIC_KEY_E = 65537


@dataclass(frozen=True, slots=True)
class TrialStatus:
    active: bool
    expired: bool
    exports_used: int
    exports_remaining: int
    expires_at: int | None
    reason: str = ""


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _state_path() -> Path:
    return writable_data_directory() / TRIAL_STATE_FILENAME


def _consumed_path() -> Path:
    return writable_data_directory() / TRIAL_CONSUMED_FILENAME


def _trial_was_consumed() -> bool:
    try:
        payload = json.loads(_unprotect(_urlsafe_decode(json.loads(_consumed_path().read_text(encoding="utf-8"))["protected"])).decode("utf-8"))
        return payload.get("machine_code") == machine_code() and bool(payload.get("consumed"))
    except (OSError, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        return False


def _mark_trial_consumed(issued_at: int) -> None:
    path = _consumed_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = _protect(json.dumps({"consumed": True, "machine_code": machine_code(), "issued_at": issued_at},
                                    sort_keys=True, separators=(",", ":")).encode("utf-8"))
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"version": 1, "protected": _urlsafe_encode(protected)}) + "\n", encoding="utf-8")
    temporary.replace(path)


def _utc_timestamp(value: datetime | None = None) -> int:
    return int((value or datetime.now(timezone.utc)).timestamp())


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def encode_trial_token(payload: dict[str, Any], signature: bytes) -> str:
    return f"{TRIAL_TOKEN_PREFIX}.{_urlsafe_encode(canonical_payload(payload))}.{_urlsafe_encode(signature)}"


def verify_trial_token(token: str, expected_machine: str | None = None) -> tuple[bool, str, dict[str, Any] | None]:
    try:
        prefix, encoded_payload, encoded_signature = token.strip().split(".", 2)
        if prefix != TRIAL_TOKEN_PREFIX:
            return False, "trial.invalid_format", None
        payload = json.loads(_urlsafe_decode(encoded_payload).decode("utf-8"))
        if not isinstance(payload, dict):
            return False, "trial.invalid_format", None
        if not _rsa_verify_with_key(
            canonical_payload(payload), _urlsafe_decode(encoded_signature), TRIAL_PUBLIC_KEY_N, TRIAL_PUBLIC_KEY_E
        ):
            return False, "trial.invalid_signature", None
        if payload.get("product") != PRODUCT_ID or payload.get("kind") != "trial":
            return False, "trial.wrong_product", None
        if expected_machine and payload.get("machine_code") != expected_machine:
            return False, "trial.wrong_machine", None
        if int(payload.get("export_limit", -1)) != TRIAL_EXPORT_LIMIT:
            return False, "trial.invalid_limits", None
        if int(payload["expires_at"]) <= int(payload["issued_at"]):
            return False, "trial.invalid_dates", None
        return True, "trial.accepted", payload
    except (KeyError, ValueError, TypeError, UnicodeError, binascii.Error, json.JSONDecodeError):
        return False, "trial.invalid_format", None


def _protect(data: bytes) -> bytes:
    """Protect local trial state with Windows DPAPI when available."""
    if os.name != "nt":
        return data
    try:
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        crypt = ctypes.windll.crypt32
        kernel = ctypes.windll.kernel32
        raw = ctypes.create_string_buffer(data)
        inp = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
        out = Blob()
        if not crypt.CryptProtectData(ctypes.byref(inp), "LongJumpReplay trial", None, None, None, 0, ctypes.byref(out)):
            return data
        result = ctypes.string_at(out.pbData, out.cbData)
        kernel.LocalFree(out.pbData)
        return result
    except Exception:
        return data


def _unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        return data
    try:
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        crypt = ctypes.windll.crypt32
        kernel = ctypes.windll.kernel32
        raw = ctypes.create_string_buffer(data)
        inp = Blob(len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
        out = Blob()
        if not crypt.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
            return data
        result = ctypes.string_at(out.pbData, out.cbData)
        kernel.LocalFree(out.pbData)
        return result
    except Exception:
        return data


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = _protect(json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    encoded = {"version": 1, "protected": _urlsafe_encode(protected)}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(encoded) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_state() -> dict[str, Any] | None:
    try:
        wrapper = json.loads(_state_path().read_text(encoding="utf-8"))
        return json.loads(_unprotect(_urlsafe_decode(wrapper["protected"])).decode("utf-8"))
    except (OSError, KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError):
        return None


def _parse_json_response(response: Any) -> dict[str, Any]:
    raw = response.read()
    return json.loads(raw.decode("utf-8"))


def fetch_worldtime_utc(opener: Callable[..., Any] = urlopen) -> int:
    request = Request(TIME_API_URL, headers={"Accept": "application/json", "User-Agent": "LongJumpReplay-trial/1"})
    with opener(request, timeout=8) as response:
        payload = _parse_json_response(response)
    if "unixtime" in payload:
        return int(payload["unixtime"])
    return _utc_timestamp(datetime.fromisoformat(str(payload["datetime"]).replace("Z", "+00:00")))


def _post_trial_registration(email: str, marketing_consent: bool, service_url: str, opener: Callable[..., Any]) -> dict[str, Any]:
    payload = {
        "product": PRODUCT_ID,
        "machine_code": machine_code(),
        "email": email.strip(),
        "marketing_consent": bool(marketing_consent),
    }
    request = Request(
        f"{service_url.rstrip('/')}/v1/trials",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "LongJumpReplay-trial/1"},
        method="POST",
    )
    try:
        with opener(request, timeout=12) as response:
            return _parse_json_response(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Trial service rejected registration ({exc.code}): {detail[:240]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Trial service is unavailable: {exc.reason}") from exc


def start_trial(
    email: str,
    marketing_consent: bool = False,
    service_url: str = TRIAL_SERVICE_URL,
    opener: Callable[..., Any] = urlopen,
    time_fetcher: Callable[[], int] = fetch_worldtime_utc,
) -> TrialStatus:
    if not EMAIL_PATTERN.fullmatch(email.strip()):
        raise ValueError("Enter a valid email address.")
    response = _post_trial_registration(email, marketing_consent, service_url, opener)
    token = str(response.get("token", ""))
    valid, reason, payload = verify_trial_token(token, machine_code())
    if not valid or payload is None:
        raise RuntimeError(f"Trial service returned an invalid token: {reason}")
    trusted_now = time_fetcher()
    if trusted_now >= int(payload["expires_at"]):
        raise RuntimeError("The trial service returned an expired trial.")
    _save_state({
        "token": token,
        "email_hash": _email_hash(email),
        "exports_used": 0,
        "last_trusted_at": trusted_now,
        "last_seen_at": trusted_now,
    })
    return trial_status(trusted_now)


def start_local_trial(time_fetcher: Callable[[], int] = lambda: int(time.time())) -> TrialStatus:
    """Start the no-registration evaluation on this computer.

    The local mode intentionally needs no email address, API, or Cloudflare
    service. State is protected with Windows DPAPI when available and remains
    bound to the machine code, matching the customer's offline workflow.
    """
    if _load_state() is not None or _trial_was_consumed():
        raise RuntimeError("The free trial has already been used on this computer.")
    issued = int(time_fetcher())
    _mark_trial_consumed(issued)
    _save_state({
        "local_trial": True,
        "machine_code": machine_code(),
        "issued_at": issued,
        "expires_at": issued + TRIAL_DURATION_SECONDS,
        "export_limit": TRIAL_EXPORT_LIMIT,
        "exports_used": 0,
        "last_trusted_at": issued,
        "last_seen_at": issued,
    })
    return trial_status(issued)


def trial_status(now: int | None = None) -> TrialStatus:
    state = _load_state()
    if not state:
        return TrialStatus(False, False, 0, 0, None, "trial.missing")
    if state.get("local_trial"):
        if state.get("machine_code") != machine_code():
            return TrialStatus(False, True, 0, 0, None, "trial.wrong_machine")
        try:
            used = int(state.get("exports_used", 0))
            limit = int(state.get("export_limit", TRIAL_EXPORT_LIMIT))
            expires_at = int(state["expires_at"])
            current = int(now if now is not None else time.time())
            last_seen = int(state.get("last_seen_at", 0))
        except (KeyError, TypeError, ValueError):
            return TrialStatus(False, True, 0, 0, None, "trial.invalid_format")
        if current < last_seen:
            return TrialStatus(False, True, used, max(0, limit - used), expires_at, "trial.clock_rollback")
        if used < 0 or used > limit or limit != TRIAL_EXPORT_LIMIT:
            return TrialStatus(False, True, used, 0, expires_at, "trial.invalid_counter")
        state["last_seen_at"] = current
        state["last_trusted_at"] = max(int(state.get("last_trusted_at", 0)), current)
        try:
            _save_state(state)
        except OSError:
            pass
        expired = current >= expires_at
        return TrialStatus(not expired, expired, used, max(0, limit - used), expires_at, "trial.expired" if expired else "")
    valid, reason, payload = verify_trial_token(str(state.get("token", "")), machine_code())
    if not valid or payload is None:
        return TrialStatus(False, True, 0, 0, None, reason)
    used = int(state.get("exports_used", 0))
    limit = int(payload["export_limit"])
    current = int(now if now is not None else time.time())
    last_seen = int(state.get("last_seen_at", 0))
    if current < last_seen:
        return TrialStatus(False, True, used, max(0, limit - used), int(payload["expires_at"]), "trial.clock_rollback")
    if used < 0 or used > limit:
        return TrialStatus(False, True, used, 0, int(payload["expires_at"]), "trial.invalid_counter")
    state["last_seen_at"] = current
    state["last_trusted_at"] = max(int(state.get("last_trusted_at", 0)), current)
    try:
        _save_state(state)
    except OSError:
        pass
    expired = current >= int(payload["expires_at"])
    return TrialStatus(not expired, expired, used, max(0, limit - used), int(payload["expires_at"]), "trial.expired" if expired else "")


def refresh_trial_status(time_fetcher: Callable[[], int] = fetch_worldtime_utc) -> TrialStatus:
    """Refresh the deadline from WorldTimeAPI, falling back to local time.

    The saved furthest-seen time prevents a backward local clock change from
    extending an offline trial. A failed network request does not interrupt a
    valid trial; it uses the local clock and the saved furthest-seen value.
    """
    state = _load_state()
    if not state:
        return trial_status()
    if state.get("local_trial"):
        # Local trials deliberately do not call an external time/API service.
        return trial_status()
    try:
        trusted_now = int(time_fetcher())
        if trusted_now < int(state.get("last_trusted_at", 0)):
            return TrialStatus(False, True, int(state.get("exports_used", 0)), 0, None, "trial.clock_rollback")
        state["last_trusted_at"] = trusted_now
        state["last_seen_at"] = max(int(state.get("last_seen_at", 0)), trusted_now)
        _save_state(state)
        return trial_status(trusted_now)
    except Exception:
        state["last_seen_at"] = max(int(state.get("last_seen_at", 0)), int(time.time()))
        try:
            _save_state(state)
        except OSError:
            pass
        return trial_status()


def trial_is_active() -> bool:
    return trial_status().active


def trial_exports_remaining() -> int:
    return trial_status().exports_remaining


def record_successful_export() -> TrialStatus:
    state = _load_state()
    status = trial_status()
    if not status.active:
        raise RuntimeError("The free trial is not active.")
    if status.exports_remaining <= 0:
        raise RuntimeError("The free trial has reached its export limit.")
    assert state is not None
    state["exports_used"] = status.exports_used + 1
    _save_state(state)
    return trial_status()
