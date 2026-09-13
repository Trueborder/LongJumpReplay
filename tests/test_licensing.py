from __future__ import annotations

import json

import pytest

import src.licensing as licensing
from src.licensing import format_activation_key_input, format_verification_code_input, machine_code, verify_license


def test_verification_code_input_keeps_six_ascii_digits() -> None:
    assert format_verification_code_input("12a 34-56789") == "123456"
    assert format_verification_code_input("１２٣45") == "45"


def test_portal_activation_key_input_is_grouped_live() -> None:
    assert format_activation_key_input("1234") == "1234-"
    assert format_activation_key_input("1234abcd") == "1234-ABCD-"
    assert format_activation_key_input("1234 abcd-2efg trailing") == "1234-ABCD-2EFG"
    assert format_activation_key_input("12x34-abio-01efg") == "1234-ABEF-G"


def test_pairing_qr_is_generated_in_memory() -> None:
    image = licensing.create_pairing_qr("https://account.example.com/dashboard/activation#pair=test-token")
    if licensing.qrcode is None:
        pytest.skip("optional QR dependency is not installed")
    assert image is not None
    assert image.mode == "RGB"
    assert image.width == image.height
    assert image.width > 100
from tools.license_admin import create_license


_TEST_PRIVATE_KEY = {
    "n": "113887575968033077093788757415164048931961548888349465058639568094382944833043784762742239896805847868686628402257331232921792155396645199893615226862091326031097818074993926693828694390507565295007986990801603482571653743736002635357023235060679773949448342027846130313417478309544936067749050571818696121991",
    "d": "68850050503585310808488496098216268957753888138859053750145714449844397428707367628970620332200858943152176896980872842033681816329937025188596293517799982971191885439239892412683061297892585895410706549028995932089459662405305859792460072764092836575863900948237878712419849940323118282746992655947920724193",
}


@pytest.fixture(autouse=True)
def isolated_license_key(tmp_path, monkeypatch):
    key_path = tmp_path / ".license_private_key.json"
    key_path.write_text(json.dumps(_TEST_PRIVATE_KEY), encoding="utf-8")
    monkeypatch.setenv("LONGJUMP_LICENSE_KEY_PATH", str(key_path))
    monkeypatch.setattr(licensing, "PUBLIC_KEY_N", int(_TEST_PRIVATE_KEY["n"]))


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
