from __future__ import annotations

import hashlib
import hmac
import io
import json
import time

import pytest

from license_service import app as license_app
from license_service import stripe_signature
from src.licensing import verify_license
from tools.generate_signing_key import generate_keypair

SECRET = "whsec_test_secret"
MACHINE = "9622-9BB8-F5FC-3CB9"


@pytest.fixture
def service(tmp_path, monkeypatch):
    """Configure the service with a throwaway key, store, and captured mail."""
    modulus, private_exponent = generate_keypair(2048)
    key_path = tmp_path / "service_key.json"
    key_path.write_text(json.dumps({"n": str(modulus), "d": str(private_exponent)}), encoding="utf-8")

    monkeypatch.setenv("LONGJUMP_SERVICE_KEY_PATH", str(key_path))
    monkeypatch.setenv("LJR_LICENSE_DB_PATH", str(tmp_path / "data.json"))
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("LJR_OWNER_EMAIL", "owner@example.com")

    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(license_app, "_send_email", lambda to, subject, body: sent.append((to, subject, body)))
    # The app trusts whichever key signed the licence, so point it at this one.
    monkeypatch.setattr("src.licensing.SERVICE_PUBLIC_KEY_N", modulus)
    return sent


def _signed_request(body: dict, secret: str = SECRET, timestamp: int | None = None) -> tuple[bytes, str]:
    raw = json.dumps(body).encode("utf-8")
    stamp = int(time.time()) if timestamp is None else timestamp
    signature = hmac.new(secret.encode(), f"{stamp}".encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, f"t={stamp},v1={signature}"


def _checkout_event(machine: str | None = MACHINE, email: str = "buyer@example.com", event_id: str = "evt_1") -> dict:
    custom_fields = []
    if machine is not None:
        custom_fields.append({"key": "machine_code", "type": "text", "text": {"value": machine}})
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "custom_fields": custom_fields,
                "customer_details": {"email": email, "name": "Jana Novakova"},
            }
        },
    }


def _call(raw: bytes, header: str) -> tuple[str, dict]:
    captured: dict[str, str] = {}

    def start_response(status, headers):
        captured["status"] = status

    environ = {
        "PATH_INFO": "/v1/stripe/webhook",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
        "HTTP_STRIPE_SIGNATURE": header,
    }
    body = license_app.application(environ, start_response)
    return captured["status"], json.loads(b"".join(body).decode("utf-8"))


def test_successful_purchase_emails_a_valid_license(service):
    raw, header = _signed_request(_checkout_event())
    status, payload = _call(raw, header)

    assert status.startswith("200")
    assert payload == {"received": "evt_1"}
    assert len(service) == 1

    to_address, subject, body = service[0]
    assert to_address == "buyer@example.com"
    assert "licence key" in subject

    key = next(line.strip() for line in body.splitlines() if line.strip().startswith("LJR2."))
    valid, reason, decoded = verify_license(key, MACHINE)
    assert (valid, reason) == (True, "license.accepted")
    assert decoded["machine_code"] == MACHINE
    assert decoded["customer"] == "Jana Novakova"


def test_issued_license_does_not_activate_another_machine(service):
    raw, header = _signed_request(_checkout_event())
    _call(raw, header)

    key = next(line.strip() for line in service[0][2].splitlines() if line.strip().startswith("LJR2."))
    valid, reason, _ = verify_license(key, "AAAA-BBBB-CCCC-DDDD")
    assert (valid, reason) == (False, "license.wrong_machine")


def test_forged_signature_is_rejected_and_issues_nothing(service):
    raw, _ = _signed_request(_checkout_event())
    _, forged_header = _signed_request(_checkout_event(), secret="whsec_wrong_secret")

    status, payload = _call(raw, forged_header)

    assert status.startswith("400")
    assert payload == {"error": "signature verification failed"}
    assert service == []


def test_unsigned_request_is_rejected(service):
    raw, _ = _signed_request(_checkout_event())
    status, _ = _call(raw, "")
    assert status.startswith("400")
    assert service == []


def test_replayed_old_timestamp_is_rejected(service):
    stale = int(time.time()) - stripe_signature.DEFAULT_TOLERANCE_SECONDS - 60
    raw, header = _signed_request(_checkout_event(), timestamp=stale)

    status, _ = _call(raw, header)

    assert status.startswith("400")
    assert service == []


def test_tampered_body_is_rejected(service):
    raw, header = _signed_request(_checkout_event())
    tampered = raw.replace(b"buyer@example.com", b"thief@example.com")
    assert tampered != raw

    status, _ = _call(tampered, header)

    assert status.startswith("400")
    assert service == []


def test_duplicate_event_only_issues_once(service):
    raw, header = _signed_request(_checkout_event())
    first_status, _ = _call(raw, header)

    raw2, header2 = _signed_request(_checkout_event())
    second_status, payload = _call(raw2, header2)

    assert first_status.startswith("200")
    assert second_status.startswith("200")
    assert payload == {"duplicate": "evt_1"}
    assert len(service) == 1


def test_malformed_machine_code_is_flagged_not_issued(service):
    raw, header = _signed_request(_checkout_event(machine="not a machine code"))
    status, _ = _call(raw, header)

    assert status.startswith("200")  # Stripe must not retry a business problem
    recipients = [entry[0] for entry in service]
    assert "buyer@example.com" not in recipients
    assert "owner@example.com" in recipients

    records = json.loads(license_app._database_path().read_text(encoding="utf-8"))
    assert records[-1]["status"] == "needs_attention"


def test_missing_machine_code_is_flagged_not_issued(service):
    raw, header = _signed_request(_checkout_event(machine=None))
    status, _ = _call(raw, header)

    assert status.startswith("200")
    assert [entry[0] for entry in service] == ["owner@example.com"]


def test_lowercase_machine_code_is_normalised(service):
    raw, header = _signed_request(_checkout_event(machine="9622-9bb8-f5fc-3cb9"))
    _call(raw, header)

    key = next(line.strip() for line in service[0][2].splitlines() if line.strip().startswith("LJR2."))
    valid, _, decoded = verify_license(key, MACHINE)
    assert valid
    assert decoded["machine_code"] == MACHINE


def test_unrelated_event_types_are_ignored(service):
    event = _checkout_event()
    event["type"] = "payment_intent.succeeded"
    raw, header = _signed_request(event)

    status, payload = _call(raw, header)

    assert status.startswith("200")
    assert payload == {"ignored": "payment_intent.succeeded"}
    assert service == []


def test_health_endpoint_reports_ok():
    captured: dict[str, str] = {}

    def start_response(status, headers):
        captured["status"] = status

    body = license_app.application({"PATH_INFO": "/health", "REQUEST_METHOD": "GET"}, start_response)

    assert captured["status"].startswith("200")
    assert json.loads(b"".join(body))["ok"] is True


def test_zero_tolerance_is_refused():
    raw, header = _signed_request(_checkout_event())
    with pytest.raises(stripe_signature.SignatureError):
        stripe_signature.verify(raw, header, SECRET, tolerance=0)


def test_v0_scheme_alone_is_not_accepted():
    raw = b'{"id":"evt_x"}'
    stamp = int(time.time())
    forged = hmac.new(SECRET.encode(), f"{stamp}".encode() + b"." + raw, hashlib.sha256).hexdigest()
    # Only v1 is a trusted scheme; a correct digest under v0 must not pass.
    with pytest.raises(stripe_signature.SignatureError):
        stripe_signature.verify(raw, f"t={stamp},v0={forged}", SECRET)
