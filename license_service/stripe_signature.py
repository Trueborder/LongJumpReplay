"""Manual Stripe webhook signature verification.

Implements the scheme documented at https://docs.stripe.com/webhooks#verify-manually
so the service keeps its no-dependency policy instead of pulling in the Stripe
SDK. Without this check anyone who learns the endpoint URL could post a forged
"payment succeeded" event and be issued a free license.
"""

from __future__ import annotations

import hashlib
import hmac
import time

# Stripe's own libraries default to five minutes. A signature older than this is
# rejected so a captured request cannot be replayed later.
DEFAULT_TOLERANCE_SECONDS = 300


class SignatureError(Exception):
    """Raised when a webhook payload is not a valid, recent Stripe signature."""


def _parse_header(header: str) -> tuple[int, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for element in header.split(","):
        prefix, _, value = element.strip().partition("=")
        if prefix == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise SignatureError("malformed timestamp") from exc
        elif prefix == "v1":
            # Only the v1 scheme is trusted. Stripe also sends a fake v0 for test
            # events; accepting other schemes would invite a downgrade attack.
            signatures.append(value)
    if timestamp is None:
        raise SignatureError("no timestamp in Stripe-Signature header")
    if not signatures:
        raise SignatureError("no v1 signature in Stripe-Signature header")
    return timestamp, signatures


def verify(
    payload: bytes,
    header: str,
    secret: str,
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
    now: float | None = None,
) -> None:
    """Raise SignatureError unless ``payload`` carries a valid recent signature.

    ``payload`` must be the exact bytes Stripe sent. Re-encoding or reformatting
    the JSON first will fail verification.
    """
    if not secret:
        raise SignatureError("no webhook signing secret configured")
    if tolerance <= 0:
        # A zero tolerance disables the recency check and re-opens replay attacks.
        raise SignatureError("tolerance must be positive")

    timestamp, signatures = _parse_header(header)
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance:
        raise SignatureError("timestamp outside tolerance")

    signed_payload = str(timestamp).encode("ascii") + b"." + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    # Stripe sends one signature per active secret while a secret is being
    # rolled, so any matching v1 signature is sufficient.
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise SignatureError("no signature matched the expected value")
