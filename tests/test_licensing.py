from __future__ import annotations

from src.licensing import machine_code, verify_license
from tools.license_admin import create_license


def test_machine_code_is_stable_and_grouped() -> None:
    value = machine_code()
    assert value == machine_code()
    assert len(value) == 19
    assert value.count("-") == 3


def test_signed_license_round_trip() -> None:
    key = create_license(machine_code(), "Test customer", "TEST-001")
    valid, reason, payload = verify_license(key, machine_code())
    assert valid, reason
    assert payload and payload["customer"] == "Test customer"


def test_license_rejects_another_machine() -> None:
    key = create_license(machine_code(), "Test customer", "TEST-002")
    valid, reason, _ = verify_license(key, "AAAA-BBBB-CCCC-DDDD")
    assert not valid
    assert reason == "license.wrong_machine"


def test_license_rejects_tampering() -> None:
    key = create_license(machine_code(), "Test customer", "TEST-003")
    prefix, payload, signature = key.split(".")
    tampered = f"{prefix}.{payload[:-1]}A.{signature}"
    valid, _, _ = verify_license(tampered, machine_code())
    assert not valid
