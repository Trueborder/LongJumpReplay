from __future__ import annotations

from io import BytesIO
import json

from trial_service.app import application


def call(path: str, method: str = "GET", payload: dict[str, object] | None = None):
    body = json.dumps(payload or {}).encode("utf-8")
    result: list[tuple[str, list[tuple[str, str]]]] = []

    def start(status, headers):
        result.append((status, headers))

    response = b"".join(application({
        "PATH_INFO": path,
        "REQUEST_METHOD": method,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }, start))
    return result[0][0], json.loads(response.decode("utf-8"))


def test_health_endpoint():
    status, body = call("/health")
    assert status == "200 OK"
    assert body["ok"] is True


def test_registration_rejects_wrong_product_before_key_access():
    status, body = call("/v1/trials", "POST", {"product": "Other", "email": "a@example.com", "machine_code": "AAAA-BBBB-CCCC-DDDD"})
    assert status == "400 Bad Request"
    assert body["error"] == "wrong product"
