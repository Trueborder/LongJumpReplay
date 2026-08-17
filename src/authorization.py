"""Local verification of server-issued activation authorizations.

The licensing API signs a short-lived authorization after a device is activated.
This module verifies it entirely offline, using the same RSA primitives as
`licensing.py`, so a competition laptop with no connectivity can start the
application without contacting anything.

The private signing key lives only in the Cloudflare Worker. Only the public
modulus is embedded here, so a copy of the EXE cannot mint authorizations.

Design note: a lifetime licence is not a permanent offline token. The licence
does not expire, but the authorization does, and is refreshed by the periodic
check. That keeps a cancelled subscription or a revoked licence from being
usable forever while still tolerating long stretches offline.
"""

from __future__ import annotations

import binascii
import json
import time
from pathlib import Path

from .licensing import PRODUCT_ID, _rsa_verify_with_key, _urlsafe_decode, canonical_payload
from .portable_paths import writable_data_directory

AUTHORIZATION_PREFIX = "LJRA1"
AUTHORIZATION_VERSION = 1

# Public half of the licensing API's authorization signing key. Filled in from
# `node scripts/generate-signing-key.mjs` when the production Worker key is
# created; until then no server authorization can verify, which is the safe
# default. The private half never leaves the Worker.
AUTHORIZATION_PUBLIC_KEY_N: int | None = None
AUTHORIZATION_PUBLIC_KEY_E = 65537

AUTHORIZATION_FILENAME = "authorization.json"


def authorization_path() -> Path:
    return writable_data_directory() / AUTHORIZATION_FILENAME


def verify_authorization(
    token: str,
    expected_machine: str | None = None,
    now: int | None = None,
    modulus: int | None = None,
) -> tuple[bool, str, dict[str, object] | None]:
    """Return (ok, reason, payload).

    ``modulus`` overrides the embedded key; it exists so tests can supply a
    throwaway key rather than requiring the production one.
    """
    key = modulus if modulus is not None else AUTHORIZATION_PUBLIC_KEY_N
    if key is None:
        return False, "authorization.no_key", None

    try:
        prefix, encoded_payload, encoded_signature = token.strip().split(".", 2)
        if prefix != AUTHORIZATION_PREFIX:
            return False, "authorization.invalid_format", None

        payload_bytes = _urlsafe_decode(encoded_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            return False, "authorization.invalid_format", None

        if not _rsa_verify_with_key(
            canonical_payload(payload),
            _urlsafe_decode(encoded_signature),
            key,
            AUTHORIZATION_PUBLIC_KEY_E,
        ):
            return False, "authorization.invalid_signature", None

        if payload.get("product") != PRODUCT_ID:
            return False, "authorization.wrong_product", None
        if payload.get("version") != AUTHORIZATION_VERSION:
            return False, "authorization.wrong_version", None
        if expected_machine and payload.get("machine_id") != expected_machine:
            return False, "authorization.wrong_machine", None

        current = int(time.time()) if now is None else now
        expires_at = payload.get("expires_at")
        if not isinstance(expires_at, int):
            return False, "authorization.invalid_format", None
        if current > expires_at:
            return False, "authorization.expired", payload

        return True, "authorization.accepted", payload
    except (ValueError, TypeError, UnicodeError, binascii.Error, json.JSONDecodeError):
        return False, "authorization.invalid_format", None


def save_authorization(token: str) -> None:
    path = authorization_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"authorization": token}), encoding="utf-8")
    temporary.replace(path)


def load_authorization() -> str | None:
    try:
        data = json.loads(authorization_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    token = data.get("authorization") if isinstance(data, dict) else None
    return token if isinstance(token, str) else None


def clear_authorization() -> None:
    try:
        authorization_path().unlink()
    except OSError:
        pass


def seconds_until_expiry(payload: dict[str, object], now: int | None = None) -> int:
    current = int(time.time()) if now is None else now
    expires_at = payload.get("expires_at")
    return int(expires_at) - current if isinstance(expires_at, int) else 0


def should_refresh(payload: dict[str, object], now: int | None = None) -> bool:
    """Refresh once past the halfway point of the authorization's life.

    Refreshing early means a laptop that is online at the club in the week
    before a competition renews quietly, instead of first discovering it needs
    a connection at the track.
    """
    issued_at = payload.get("issued_at")
    expires_at = payload.get("expires_at")
    if not isinstance(issued_at, int) or not isinstance(expires_at, int):
        return True
    current = int(time.time()) if now is None else now
    return current >= issued_at + (expires_at - issued_at) // 2
