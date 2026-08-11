from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.licensing import PRODUCT_ID, SUPPORTED_MAJOR_VERSION, canonical_payload, encode_license


PRIVATE_KEY_PATH = Path(__file__).with_name(".license_private_key.json")


def private_key_path() -> Path:
    """Return the private-key sidecar path for source and frozen admin tools."""
    configured = os.environ.get("LONGJUMP_LICENSE_KEY_PATH")
    if configured:
        return Path(configured).expanduser()
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        candidates = (
            executable_dir / ".license_private_key.json",
            executable_dir / "tools" / ".license_private_key.json",
            executable_dir.parent.parent / "tools" / ".license_private_key.json",
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]
    return PRIVATE_KEY_PATH


def _sign(message: bytes, private_key: dict[str, str]) -> bytes:
    n = int(private_key["n"])
    d = int(private_key["d"])
    size = (n.bit_length() + 7) // 8
    from src.licensing import _encoded_message
    encoded = _encoded_message(message, size)
    return pow(int.from_bytes(encoded, "big"), d, n).to_bytes(size, "big")


def create_license(machine: str, customer: str, license_id: str) -> str:
    key_path = private_key_path()
    private_key = json.loads(key_path.read_text(encoding="utf-8"))
    payload = {
        "product": PRODUCT_ID,
        "major_version": SUPPORTED_MAJOR_VERSION,
        "license_id": license_id,
        "customer": customer,
        "machine_code": machine.upper(),
        "issued": date.today().isoformat(),
    }
    return encode_license(payload, _sign(canonical_payload(payload), private_key))


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an offline LongJumpReplay license key")
    parser.add_argument("--machine", required=True, help="Machine code shown by the application")
    parser.add_argument("--customer", required=True, help="Customer or organization name")
    parser.add_argument("--license-id", required=True, help="Your internal license identifier")
    args = parser.parse_args()
    if not private_key_path().exists():
        raise SystemExit(f"Private key not found: {private_key_path()}")
    print(create_license(args.machine, args.customer, args.license_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
