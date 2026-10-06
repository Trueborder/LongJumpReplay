"""Dependency-free WSGI service that issues licenses after a Stripe purchase.

The customer pastes the machine code shown in the app into a custom field at
Stripe checkout. On ``checkout.session.completed`` this service signs a licence
bound to that machine code and emails it to them.

Run behind HTTPS. Required configuration:

    LONGJUMP_SERVICE_KEY_PATH   private RSA JSON key ({"n", "d"}) - never commit
    STRIPE_WEBHOOK_SECRET       endpoint signing secret, starts with whsec_
    LJR_SMTP_HOST               outbound mail host
    LJR_SMTP_USER               mail username
    LJR_SMTP_PASSWORD           mail password
    LJR_MAIL_FROM               sender address shown to the customer

Optional:

    LJR_LICENSE_DB_PATH         order store (default license_service/data.json)
    LJR_MACHINE_FIELD_KEY       Stripe custom field key (default machine_code)
    LJR_SMTP_PORT               default 587
    LJR_OWNER_EMAIL             notified when an order needs manual attention
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from email.message import EmailMessage
import json
import logging
import os
from pathlib import Path
import re
import smtplib
from threading import Lock

from license_service import stripe_signature
from src.licensing import PRODUCT_ID, SUPPORTED_MAJOR_VERSION, _encoded_message, canonical_payload, encode_license

LOGGER = logging.getLogger("longjumpreplay.license_service")

# Machine codes are four groups of four uppercase hex digits, per machine_code().
MACHINE_PATTERN = re.compile(r"^[0-9A-F]{4}(?:-[0-9A-F]{4}){3}$")
MAX_BODY_BYTES = 262_144
_LOCK = Lock()


def _database_path() -> Path:
    return Path(os.environ.get("LJR_LICENSE_DB_PATH", "license_service/data.json")).expanduser()


def _private_key_path() -> Path:
    configured = os.environ.get("LONGJUMP_SERVICE_KEY_PATH")
    if not configured:
        raise RuntimeError("LONGJUMP_SERVICE_KEY_PATH is not configured")
    return Path(configured).expanduser()


def _machine_field_key() -> str:
    return os.environ.get("LJR_MACHINE_FIELD_KEY", "machine_code")


def _sign(payload: dict[str, object]) -> bytes:
    private = json.loads(_private_key_path().read_text(encoding="utf-8"))
    modulus, private_exponent = int(private["n"]), int(private["d"])
    size = (modulus.bit_length() + 7) // 8
    encoded = _encoded_message(canonical_payload(payload), size)
    return pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(size, "big")


def create_license(machine: str, customer: str, license_id: str) -> str:
    """Sign a licence bound to ``machine``, matching the offline tool's payload."""
    payload = {
        "product": PRODUCT_ID,
        "major_version": SUPPORTED_MAJOR_VERSION,
        "license_id": license_id,
        "customer": customer,
        "machine_code": machine.upper(),
        "issued": date.today().isoformat(),
    }
    return encode_license(payload, _sign(payload))


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


def _send_email(to_address: str, subject: str, body: str) -> None:
    host = os.environ.get("LJR_SMTP_HOST")
    sender = os.environ.get("LJR_MAIL_FROM")
    if not host or not sender:
        raise RuntimeError("LJR_SMTP_HOST and LJR_MAIL_FROM must be configured")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to_address
    message.set_content(body)

    port = int(os.environ.get("LJR_SMTP_PORT", "587"))
    username = os.environ.get("LJR_SMTP_USER")
    password = os.environ.get("LJR_SMTP_PASSWORD")
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)


def _license_email_body(customer: str, machine: str, key: str) -> str:
    greeting = f"Hello {customer}," if customer else "Hello,"
    return (
        f"{greeting}\n\n"
        "Thank you for buying LongJumpReplay. Your licence key is below.\n\n"
        f"    {key}\n\n"
        "To activate: open LongJumpReplay, choose paid activation, and paste the\n"
        "key into the activation window.\n\n"
        f"This key is tied to machine code {machine} and will only activate that\n"
        "computer. If you need it moved to a different computer, reply to this\n"
        "email with the new machine code.\n\n"
        "Novaryn Solutions\n"
        "https://tomaspisar.cz\n"
    )


def _extract_machine_code(session: dict[str, object]) -> str | None:
    wanted = _machine_field_key()
    fields = session.get("custom_fields")
    if not isinstance(fields, list):
        return None
    for field in fields:
        if not isinstance(field, dict) or field.get("key") != wanted:
            continue
        text = field.get("text")
        if isinstance(text, dict):
            value = text.get("value")
            if isinstance(value, str):
                # Customers paste this by hand, so tolerate spacing and case.
                return value.strip().upper().replace(" ", "")
    return None


def _fulfil(session: dict[str, object], event_id: str) -> None:
    """Issue and email a licence. Records the order before anything can fail."""
    details = session.get("customer_details")
    details = details if isinstance(details, dict) else {}
    email = str(details.get("email") or "").strip()
    customer = str(details.get("name") or "").strip()
    machine = _extract_machine_code(session)
    session_id = str(session.get("id") or "")
    license_id = session_id or event_id

    record: dict[str, object] = {
        "event_id": event_id,
        "session_id": session_id,
        "email": email,
        "customer": customer,
        "machine_code": machine,
        "license_id": license_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "status": "received",
    }

    problem: str | None = None
    if not email:
        problem = "no customer email on the checkout session"
    elif machine is None:
        problem = f"no {_machine_field_key()} custom field on the checkout session"
    elif not MACHINE_PATTERN.fullmatch(machine):
        problem = f"machine code {machine!r} is not in the expected format"

    if problem is None:
        try:
            key = create_license(machine, customer, license_id)
            _send_email(email, "Your LongJumpReplay licence key", _license_email_body(customer, machine, key))
            record["status"] = "fulfilled"
            record["issued_key"] = key
        except Exception as exc:  # noqa: BLE001 - any failure must still be recorded
            problem = f"{type(exc).__name__}: {exc}"

    if problem is not None:
        record["status"] = "needs_attention"
        record["problem"] = problem
        LOGGER.error("order %s needs manual attention: %s", license_id, problem)

    with _LOCK:
        records = _read_records()
        records.append(record)
        _write_records(records)

    if problem is not None:
        _notify_owner(record, problem)


def _notify_owner(record: dict[str, object], problem: str) -> None:
    owner = os.environ.get("LJR_OWNER_EMAIL")
    if not owner:
        return
    try:
        _send_email(
            owner,
            "LongJumpReplay order needs attention",
            "An order could not be fulfilled automatically.\n\n"
            f"Problem     : {problem}\n"
            f"Session     : {record.get('session_id')}\n"
            f"Customer    : {record.get('customer')}\n"
            f"Email       : {record.get('email')}\n"
            f"Machine code: {record.get('machine_code')}\n\n"
            "Issue the licence manually with the license generator once resolved.\n",
        )
    except Exception:  # noqa: BLE001 - never let the notification break the webhook
        LOGGER.exception("could not notify the owner about order %s", record.get("license_id"))


def _already_processed(event_id: str) -> bool:
    return any(record.get("event_id") == event_id for record in _read_records())


def _json(start_response, status: str, payload: dict[str, object]):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def _webhook(environ, start_response):
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return _json(start_response, "400 Bad Request", {"error": "bad content length"})
    if length > MAX_BODY_BYTES:
        return _json(start_response, "400 Bad Request", {"error": "request too large"})

    raw = environ["wsgi.input"].read(length)
    header = environ.get("HTTP_STRIPE_SIGNATURE", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    try:
        stripe_signature.verify(raw, header, secret)
    except stripe_signature.SignatureError as exc:
        LOGGER.warning("rejected webhook: %s", exc)
        return _json(start_response, "400 Bad Request", {"error": "signature verification failed"})

    try:
        event = json.loads(raw.decode("utf-8"))
        if not isinstance(event, dict):
            raise ValueError("event must be a JSON object")
    except (ValueError, UnicodeError):
        return _json(start_response, "400 Bad Request", {"error": "invalid JSON"})

    event_id = str(event.get("id") or "")
    if event.get("type") != "checkout.session.completed":
        return _json(start_response, "200 OK", {"ignored": event.get("type")})

    # Stripe retries until it gets a 2xx, so the same event can arrive twice.
    with _LOCK:
        if event_id and _already_processed(event_id):
            return _json(start_response, "200 OK", {"duplicate": event_id})

    session = event.get("data", {}).get("object") if isinstance(event.get("data"), dict) else None
    if not isinstance(session, dict):
        return _json(start_response, "400 Bad Request", {"error": "no checkout session in event"})

    try:
        _fulfil(session, event_id)
    except Exception:  # noqa: BLE001
        # Returning 5xx makes Stripe retry, which is what we want for a genuine
        # outage. Business problems are recorded inside _fulfil and return 200.
        LOGGER.exception("failed to process event %s", event_id)
        return _json(start_response, "503 Service Unavailable", {"error": "temporary failure"})

    return _json(start_response, "200 OK", {"received": event_id})


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    method = environ.get("REQUEST_METHOD", "GET").upper()
    if path == "/health" and method == "GET":
        return _json(start_response, "200 OK", {"ok": True, "service": "longjumpreplay-license"})
    if path == "/v1/stripe/webhook" and method == "POST":
        return _webhook(environ, start_response)
    return _json(start_response, "404 Not Found", {"error": "not found"})


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", "8081"))
    with make_server("127.0.0.1", port, application) as server:
        print(f"LongJumpReplay license service listening on http://127.0.0.1:{port}")
        server.serve_forever()
