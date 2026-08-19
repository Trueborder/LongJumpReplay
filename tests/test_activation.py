"""Activation client tests.

The network layer is exercised through a fake opener that mirrors the Worker's
real responses, including its error shapes, so the client is tested against the
contract it actually has to satisfy.
"""

from __future__ import annotations

import io
import json
import re

import pytest

from src import activation
from src.activation import ActivationError, device_id, device_name


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def responder(mapping: dict[str, object], record: list | None = None):
    """Build an opener returning canned JSON per path."""

    def opener(request, timeout=None):
        path = request.full_url.split("tomaspisar.cz", 1)[-1]
        if record is not None:
            record.append((path, json.loads(request.data.decode("utf-8"))))
        value = mapping[path]
        if isinstance(value, Exception):
            raise value
        return FakeResponse(json.dumps(value).encode("utf-8"))

    return opener


def test_device_id_is_stable_and_server_acceptable():
    first, second = device_id(), device_id()
    assert first == second
    # Must satisfy the Worker's ^[A-Za-z0-9_-]{16,128}$
    assert re.fullmatch(r"[A-Za-z0-9_-]{16,128}", first)


def test_device_id_leaks_no_raw_identifiers():
    import platform
    import uuid

    identifier = device_id()
    for raw in (platform.node(), str(uuid.getnode())):
        if raw:
            assert raw not in identifier


def test_device_name_is_bounded():
    name = device_name()
    assert name is None or len(name) <= 64


def test_request_code_returns_expiry(monkeypatch):
    opener = responder({"/api/license/request-code": {"sent": True, "expires_in_minutes": 10}})
    assert activation.request_code("buyer@example.com", opener) == 10


def test_verify_code_returns_grant():
    opener = responder({"/api/license/verify-code": {"verified": True, "activation_grant": "g" * 40}})
    assert activation.verify_code("buyer@example.com", "123456", opener) == "g" * 40


def test_verify_code_without_grant_is_an_error():
    opener = responder({"/api/license/verify-code": {"verified": True}})
    with pytest.raises(ActivationError):
        activation.verify_code("buyer@example.com", "123456", opener)


def test_activate_sends_derived_device_id_not_raw_hardware():
    record: list = []
    opener = responder(
        {"/api/license/activate": {"activated": True, "license_type": "lifetime", "max_devices": 2}},
        record,
    )
    # No authorization in the response, so activate() must refuse.
    with pytest.raises(ActivationError):
        activation.activate("grant", opener)

    path, payload = record[0]
    assert path == "/api/license/activate"
    assert payload["machine_id"] == device_id()
    assert "machine_code" not in payload


def test_activate_refuses_an_unverifiable_authorization(monkeypatch):
    """A token the app cannot verify must not be stored.

    Otherwise activation would appear to succeed and then fail on next launch,
    which is the worst possible failure mode for a competition morning.
    """
    saved: list[str] = []
    monkeypatch.setattr(activation, "save_authorization", lambda token: saved.append(token))
    monkeypatch.setattr(activation, "verify_authorization", lambda *a, **k: (False, "authorization.invalid_signature", None))

    opener = responder(
        {
            "/api/license/activate": {
                "activated": True,
                "license_type": "lifetime",
                "max_devices": 2,
                "authorization": "LJRA1.aaa.bbb",
            }
        }
    )
    with pytest.raises(ActivationError):
        activation.activate("grant", opener)
    assert saved == []


def test_activate_stores_a_verifiable_authorization(monkeypatch):
    saved: list[str] = []
    monkeypatch.setattr(activation, "save_authorization", lambda token: saved.append(token))
    monkeypatch.setattr(activation, "verify_authorization", lambda *a, **k: (True, "authorization.accepted", {}))

    opener = responder(
        {
            "/api/license/activate": {
                "activated": True,
                "license_type": "subscription",
                "max_devices": 2,
                "authorization": "LJRA1.aaa.bbb",
            }
        }
    )
    result = activation.activate("grant", opener)
    assert result.license_type == "subscription"
    assert result.max_devices == 2
    assert saved == ["LJRA1.aaa.bbb"]


def test_server_error_message_is_shown_to_the_customer():
    from urllib.error import HTTPError

    error = HTTPError(
        "https://api.tomaspisar.cz/api/license/activate",
        409,
        "Conflict",
        {},
        io.BytesIO(
            json.dumps(
                {"error": "device_limit", "message": "This licence is already active on 2 computers."}
            ).encode()
        ),
    )
    opener = responder({"/api/license/activate": error})
    with pytest.raises(ActivationError) as raised:
        activation.activate("grant", opener)
    assert "already active on 2 computers" in str(raised.value)
    assert raised.value.code == "device_limit"


def test_offline_is_reported_as_a_connection_problem():
    from urllib.error import URLError

    opener = responder({"/api/license/request-code": URLError("no route to host")})
    with pytest.raises(ActivationError) as raised:
        activation.request_code("buyer@example.com", opener)
    assert raised.value.code == "offline"
    assert "internet connection" in str(raised.value)


def test_refresh_if_due_is_silent_when_offline(monkeypatch):
    """A laptop at a track must keep working when the refresh cannot happen."""
    from urllib.error import URLError

    monkeypatch.setattr(
        activation,
        "current_authorization",
        lambda: (True, "authorization.accepted", {"license_id": "lic_1", "issued_at": 0, "expires_at": 100}),
    )
    opener = responder({"/api/license/verify": URLError("offline")})
    activation.refresh_if_due(opener)  # must not raise


def test_refresh_if_due_does_nothing_when_not_due(monkeypatch):
    called: list = []
    monkeypatch.setattr(
        activation,
        "current_authorization",
        lambda: (True, "authorization.accepted", {"license_id": "lic_1", "issued_at": 0, "expires_at": 10**12}),
    )
    monkeypatch.setattr(activation, "refresh", lambda *a, **k: called.append(1))
    activation.refresh_if_due()
    assert called == []


def test_startup_check_verifies_online_on_every_launch(monkeypatch):
    payload = {"license_id": "lic_1", "issued_at": 1, "expires_at": 10**12}
    calls: list[str] = []
    monkeypatch.setattr(activation, "current_authorization", lambda: (True, "authorization.accepted", payload))
    monkeypatch.setattr(activation, "refresh", lambda license_id, opener: calls.append(license_id) or True)

    result = activation.check_startup_authorization(opener=object())

    assert result.state == "verified"
    assert result.allowed
    assert calls == ["lic_1"]


def test_startup_check_uses_valid_signed_authorization_when_offline(monkeypatch):
    payload = {"license_id": "lic_1", "issued_at": 1, "expires_at": 10**12}
    monkeypatch.setattr(activation, "current_authorization", lambda: (True, "authorization.accepted", payload))

    def offline(*_args, **_kwargs):
        raise ActivationError("offline", "offline")

    monkeypatch.setattr(activation, "refresh", offline)
    result = activation.check_startup_authorization()
    assert result.state == "cached"
    assert result.allowed


@pytest.mark.parametrize("code", ["no_license", "device_not_active", "license_inactive"])
def test_startup_check_blocks_explicit_server_rejection(monkeypatch, code):
    payload = {"license_id": "lic_1", "issued_at": 1, "expires_at": 10**12}
    cleared: list[bool] = []
    monkeypatch.setattr(activation, "current_authorization", lambda: (True, "authorization.accepted", payload))
    monkeypatch.setattr(activation, "clear_authorization", lambda: cleared.append(True))

    def rejected(*_args, **_kwargs):
        raise ActivationError("rejected", code)

    monkeypatch.setattr(activation, "refresh", rejected)
    result = activation.check_startup_authorization()
    assert result.state == "rejected"
    assert not result.allowed
    assert cleared == [True]


def test_startup_check_does_not_contact_server_without_authorization(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(activation, "current_authorization", lambda: (False, "authorization.missing", None))
    monkeypatch.setattr(activation, "refresh", lambda *_args, **_kwargs: calls.append(True))
    result = activation.check_startup_authorization()
    assert result.state == "missing"
    assert not result.allowed
    assert calls == []


def test_customer_portal_url_opens_the_dedicated_login_route():
    assert activation.PORTAL_LOGIN_URL == "https://account.tomaspisar.cz/login"
