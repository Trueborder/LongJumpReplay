"""Dependency-free WSGI service for issuing signed evaluation tokens.

Run behind HTTPS in production. The service needs LONGJUMP_TRIAL_KEY_PATH
pointing to a private RSA JSON key with ``n`` and ``d`` fields. Never commit
that file. The public key is embedded in ``src.trial`` for verification.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Lock
import uuid

from src.licensing import _encoded_message, canonical_payload
from src.trial import PRODUCT_ID, TRIAL_DURATION_SECONDS, TRIAL_EXPORT_LIMIT, encode_trial_token

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MACHINE_PATTERN = re.compile(r"^[0-9A-F]{4}(?:-[0-9A-F]{4}){3}$")
_LOCK = Lock()


def _database_path() -> Path:
    return Path(os.environ.get("LJR_TRIAL_DB_PATH", "trial_service/data.json")).expanduser()


def _private_key_path() -> Path:
    configured = os.environ.get("LONGJUMP_TRIAL_KEY_PATH")
    if not configured:
        raise RuntimeError("LONGJUMP_TRIAL_KEY_PATH is not configured")
    return Path(configured).expanduser()


def _sign(payload: dict[str, object]) -> bytes:
    private = json.loads(_private_key_path().read_text(encoding="utf-8"))
    n, d = int(private["n"]), int(private["d"])
    size = (n.bit_length() + 7) // 8
    encoded = _encoded_message(canonical_payload(payload), size)
    return pow(int.from_bytes(encoded, "big"), d, n).to_bytes(size, "big")


def _read_records() -> list[dict[str, object]]:
    try:
        value = json.loads(_database_path().read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def _write_records(records: list[dict[str, object]]) -> None:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _json(start_response, status: str, payload: dict[str, object]):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(status, [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body))), ("Cache-Control", "no-store")])
    return [body]


def _request_json(environ) -> dict[str, object]:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    if length > 16_384:
        raise ValueError("request too large")
    raw = environ["wsgi.input"].read(length)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _register(environ, start_response):
    try:
        request = _request_json(environ)
        email = str(request.get("email", "")).strip().lower()
        machine = str(request.get("machine_code", "")).strip().upper()
        if request.get("product") != PRODUCT_ID:
            return _json(start_response, "400 Bad Request", {"error": "wrong product"})
        if not EMAIL_PATTERN.fullmatch(email) or not MACHINE_PATTERN.fullmatch(machine):
            return _json(start_response, "400 Bad Request", {"error": "valid email and machine_code are required"})
        email_hash = hashlib.sha256(email.encode("utf-8")).hexdigest()
        with _LOCK:
            records = _read_records()
            if any(record.get("machine_code") == machine or record.get("email_hash") == email_hash for record in records):
                return _json(start_response, "409 Conflict", {"error": "a trial has already been registered for this email or machine"})
            issued = int(datetime.now(timezone.utc).timestamp())
            payload = {
                "product": PRODUCT_ID,
                "kind": "trial",
                "trial_id": str(uuid.uuid4()),
                "machine_code": machine,
                "email_hash": email_hash,
                "issued_at": issued,
                "expires_at": issued + TRIAL_DURATION_SECONDS,
                "export_limit": TRIAL_EXPORT_LIMIT,
                "major_version": "3",
            }
            token = encode_trial_token(payload, _sign(payload))
            records.append({
                "trial_id": payload["trial_id"],
                "email": email,
                "email_hash": email_hash,
                "machine_code": machine,
                "marketing_consent": bool(request.get("marketing_consent", False)),
                "issued_at": issued,
                "expires_at": payload["expires_at"],
            })
            _write_records(records)
        return _json(start_response, "201 Created", {"token": token, "trial_id": payload["trial_id"], "expires_at": payload["expires_at"]})
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return _json(start_response, "400 Bad Request", {"error": str(exc)})
    except (OSError, RuntimeError) as exc:
        return _json(start_response, "503 Service Unavailable", {"error": str(exc)})


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "GET").upper()
    if path == "/health" and method == "GET":
        return _json(start_response, "200 OK", {"ok": True, "service": "longjumpreplay-trial"})
    if path == "/v1/trials" and method == "POST":
        return _register(environ, start_response)
    return _json(start_response, "404 Not Found", {"error": "not found"})


if __name__ == "__main__":
    from wsgiref.simple_server import make_server
    port = int(os.environ.get("PORT", "8080"))
    with make_server("127.0.0.1", port, application) as server:
        print(f"LongJumpReplay trial service listening on http://127.0.0.1:{port}")
        server.serve_forever()
