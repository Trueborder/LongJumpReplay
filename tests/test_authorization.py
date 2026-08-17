"""Verify server-issued authorizations exactly as the shipped app would.

The signing side is the Cloudflare Worker (RSASSA-PKCS1-v1_5 / SHA-256 via
WebCrypto); these tests reproduce that signature in Python so the verifier is
exercised against genuinely valid input, and against every way it should fail.
"""

from __future__ import annotations

import json
import time

import pytest

from src.authorization import (
    AUTHORIZATION_PREFIX,
    AUTHORIZATION_VERSION,
    seconds_until_expiry,
    should_refresh,
    verify_authorization,
)
from src.licensing import PRODUCT_ID, _encoded_message, _urlsafe_encode, canonical_payload
from tools.generate_signing_key import generate_keypair


@pytest.fixture(scope="module")
def keypair():
    return generate_keypair(2048)


def make_token(keypair, payload: dict, corrupt_signature: bool = False) -> str:
    modulus, private_exponent = keypair
    message = canonical_payload(payload)
    size = (modulus.bit_length() + 7) // 8
    encoded = _encoded_message(message, size)
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(size, "big")
    if corrupt_signature:
        signature = bytes([signature[0] ^ 0x01]) + signature[1:]
    return f"{AUTHORIZATION_PREFIX}.{_urlsafe_encode(message)}.{_urlsafe_encode(signature)}"


def payload_for(machine: str = "bWFjaGluZUFhYWFhYWFhYWFh", **overrides) -> dict:
    issued = int(time.time())
    base = {
        "product": PRODUCT_ID,
        "version": AUTHORIZATION_VERSION,
        "license_id": "lic_test",
        "license_type": "lifetime",
        "machine_id": machine,
        "max_devices": 2,
        "issued_at": issued,
        "expires_at": issued + 30 * 86400,
    }
    base.update(overrides)
    return base


def test_valid_authorization_is_accepted(keypair):
    modulus, _ = keypair
    payload = payload_for()
    ok, reason, decoded = verify_authorization(
        make_token(keypair, payload), payload["machine_id"], modulus=modulus
    )
    assert (ok, reason) == (True, "authorization.accepted")
    assert decoded["license_id"] == "lic_test"


def test_tampered_payload_is_rejected(keypair):
    modulus, _ = keypair
    payload = payload_for()
    token = make_token(keypair, payload)

    forged = dict(payload, max_devices=99)
    prefix, _, signature = token.split(".", 2)
    tampered = f"{prefix}.{_urlsafe_encode(canonical_payload(forged))}.{signature}"

    ok, reason, _ = verify_authorization(tampered, payload["machine_id"], modulus=modulus)
    assert (ok, reason) == (False, "authorization.invalid_signature")


def test_corrupt_signature_is_rejected(keypair):
    modulus, _ = keypair
    payload = payload_for()
    ok, reason, _ = verify_authorization(
        make_token(keypair, payload, corrupt_signature=True), payload["machine_id"], modulus=modulus
    )
    assert (ok, reason) == (False, "authorization.invalid_signature")


def test_authorization_for_another_machine_is_rejected(keypair):
    modulus, _ = keypair
    payload = payload_for()
    ok, reason, _ = verify_authorization(
        make_token(keypair, payload), "c29tZW90aGVybWFjaGluZQ", modulus=modulus
    )
    assert (ok, reason) == (False, "authorization.wrong_machine")


def test_expired_authorization_is_rejected(keypair):
    modulus, _ = keypair
    issued = int(time.time()) - 40 * 86400
    payload = payload_for(issued_at=issued, expires_at=issued + 30 * 86400)
    ok, reason, decoded = verify_authorization(
        make_token(keypair, payload), payload["machine_id"], modulus=modulus
    )
    assert (ok, reason) == (False, "authorization.expired")
    # The payload is still returned so the app can explain what expired.
    assert decoded is not None


def test_authorization_signed_by_another_key_is_rejected(keypair):
    other_modulus, _ = generate_keypair(2048)
    payload = payload_for()
    ok, reason, _ = verify_authorization(
        make_token(keypair, payload), payload["machine_id"], modulus=other_modulus
    )
    assert (ok, reason) == (False, "authorization.invalid_signature")


def test_wrong_product_and_version_are_rejected(keypair):
    modulus, _ = keypair
    wrong_product = payload_for(product="SomethingElse")
    ok, reason, _ = verify_authorization(
        make_token(keypair, wrong_product), wrong_product["machine_id"], modulus=modulus
    )
    assert (ok, reason) == (False, "authorization.wrong_product")

    wrong_version = payload_for(version=99)
    ok, reason, _ = verify_authorization(
        make_token(keypair, wrong_version), wrong_version["machine_id"], modulus=modulus
    )
    assert (ok, reason) == (False, "authorization.wrong_version")


def test_malformed_tokens_are_rejected(keypair):
    modulus, _ = keypair
    for bad in ["", "nonsense", "LJRA1.only-two-parts", "WRONG.aaa.bbb", "LJRA1...."]:
        ok, reason, _ = verify_authorization(bad, modulus=modulus)
        assert ok is False, bad
        assert reason.startswith("authorization."), bad


def test_production_key_is_embedded():
    """The shipped build must carry the server's public key.

    If this is None the app fails closed and no customer can activate, so it is
    worth failing the build rather than shipping that quietly.
    """
    from src.authorization import AUTHORIZATION_PUBLIC_KEY_N

    assert AUTHORIZATION_PUBLIC_KEY_N is not None
    assert AUTHORIZATION_PUBLIC_KEY_N.bit_length() >= 2048


def test_token_signed_by_a_foreign_key_is_rejected_by_the_embedded_key(keypair):
    """A throwaway key must not verify against the embedded production one."""
    payload = payload_for()
    ok, reason, _ = verify_authorization(make_token(keypair, payload), payload["machine_id"])
    assert (ok, reason) == (False, "authorization.invalid_signature")


def test_missing_key_fails_closed(keypair, monkeypatch):
    """With no embedded key nothing may verify, whatever the token says."""
    monkeypatch.setattr("src.authorization.AUTHORIZATION_PUBLIC_KEY_N", None)
    payload = payload_for()
    ok, reason, _ = verify_authorization(make_token(keypair, payload), payload["machine_id"])
    assert (ok, reason) == (False, "authorization.no_key")


def test_refresh_is_due_after_half_the_window():
    issued = 1_000_000
    payload = {"issued_at": issued, "expires_at": issued + 30 * 86400}
    assert should_refresh(payload, now=issued + 1) is False
    assert should_refresh(payload, now=issued + 14 * 86400) is False
    assert should_refresh(payload, now=issued + 16 * 86400) is True


def test_seconds_until_expiry():
    payload = {"issued_at": 1_000_000, "expires_at": 1_000_600}
    assert seconds_until_expiry(payload, now=1_000_100) == 500
