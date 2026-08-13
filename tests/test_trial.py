from __future__ import annotations

import json
import math
import secrets
import time

import pytest

import src.trial as trial
from src.licensing import _encoded_message, canonical_payload


def _prime(bits: int) -> int:
    def probable(n: int) -> bool:
        if n < 2 or n % 2 == 0:
            return n == 2
        d, rounds = n - 1, 0
        while d % 2 == 0:
            d //= 2
            rounds += 1
        for _ in range(16):
            a = secrets.randbelow(n - 3) + 2
            x = pow(a, d, n)
            if x in (1, n - 1):
                continue
            for _ in range(rounds - 1):
                x = pow(x, 2, n)
                if x == n - 1:
                    break
            else:
                return False
        return True

    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if probable(candidate):
            return candidate


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(trial, "writable_data_directory", lambda: tmp_path)
    monkeypatch.setattr(trial, "machine_code", lambda: "AAAA-BBBB-CCCC-DDDD")
    p, q = _prime(512), _prime(512)
    n = p * q
    e = 65537
    d = pow(e, -1, (p - 1) * (q - 1))
    monkeypatch.setattr(trial, "TRIAL_PUBLIC_KEY_N", n)
    return n, d


def _token(key: tuple[int, int], machine: str, issued: int = 1_700_000_000) -> str:
    n, d = key
    payload = {
        "product": "LongJumpReplay",
        "kind": "trial",
        "trial_id": "trial-test",
        "machine_code": machine,
        "email_hash": "e" * 64,
        "issued_at": issued,
        "expires_at": issued + trial.TRIAL_DURATION_SECONDS,
        "export_limit": trial.TRIAL_EXPORT_LIMIT,
        "major_version": "3",
    }
    size = (n.bit_length() + 7) // 8
    signature = pow(
        int.from_bytes(_encoded_message(canonical_payload(payload), size), "big"), d, n
    ).to_bytes(size, "big")
    return trial.encode_trial_token(payload, signature)


def test_signed_trial_token_round_trip_and_tamper_rejection(isolated_state):
    token = _token(isolated_state, "AAAA-BBBB-CCCC-DDDD")
    valid, reason, payload = trial.verify_trial_token(token, "AAAA-BBBB-CCCC-DDDD")
    assert valid, reason
    assert payload and payload["export_limit"] == 3

    prefix, encoded, signature = token.split(".")
    tampered = f"{prefix}.{encoded[:-1]}A.{signature}"
    valid, reason, _ = trial.verify_trial_token(tampered, "AAAA-BBBB-CCCC-DDDD")
    assert not valid
    assert reason in {"trial.invalid_signature", "trial.invalid_format"}


def test_trial_registration_starts_72_hour_state(isolated_state):
    token = _token(isolated_state, "AAAA-BBBB-CCCC-DDDD", issued=1_700_000_000)

    def opener(_request, timeout=0):
        assert timeout == 12
        return _Response({"token": token})

    status = trial.start_trial(
        "tester@example.com",
        service_url="https://trial.example",
        opener=opener,
        time_fetcher=lambda: 1_700_000_010,
    )
    assert status.active
    assert status.exports_remaining == 3
    assert status.expires_at == 1_700_000_000 + trial.TRIAL_DURATION_SECONDS


def test_successful_exports_are_counted_and_fourth_is_blocked(isolated_state):
    issued = int(time.time())
    token = _token(isolated_state, "AAAA-BBBB-CCCC-DDDD", issued=issued)
    trial._save_state({"token": token, "exports_used": 0, "last_trusted_at": issued, "last_seen_at": issued})
    assert [trial.record_successful_export().exports_remaining for _ in range(3)] == [2, 1, 0]
    with pytest.raises(RuntimeError, match="export limit"):
        trial.record_successful_export()


def test_clock_rollback_invalidates_trial(isolated_state):
    token = _token(isolated_state, "AAAA-BBBB-CCCC-DDDD", issued=1_700_000_000)
    trial._save_state({"token": token, "exports_used": 0, "last_trusted_at": 1_700_000_100, "last_seen_at": 1_700_000_100})
    status = trial.refresh_trial_status(lambda: 1_700_000_099)
    assert not status.active
    assert status.reason == "trial.clock_rollback"


def test_failed_export_does_not_consume_slot(isolated_state):
    issued = int(time.time())
    token = _token(isolated_state, "AAAA-BBBB-CCCC-DDDD", issued=issued)
    trial._save_state({"token": token, "exports_used": 0, "last_trusted_at": issued, "last_seen_at": issued})
    assert trial.trial_status(issued + 20).exports_used == 0
