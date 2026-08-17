"""Generate an RSA signing keypair for LongJumpReplay licensing.

Writes the private half as {"n": ..., "d": ...} JSON and prints the public
modulus to embed in src/licensing.py. Used for the offline owner key and for
the online license-service key, which are deliberately different keys.

    py -3.12 tools/generate_signing_key.py tools/.license_service_private_key.json

The output path must stay untracked. Refuses to overwrite an existing file so a
live signing key cannot be destroyed by a stray re-run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import sys

PUBLIC_EXPONENT = 65537
DEFAULT_BITS = 2048
_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)


def is_probable_prime(candidate: int, rounds: int = 64) -> bool:
    """Miller-Rabin with enough rounds that a composite is not a real risk."""
    if candidate < 2:
        return False
    for prime in _SMALL_PRIMES:
        if candidate % prime == 0:
            return candidate == prime
    remainder, power = candidate - 1, 0
    while remainder % 2 == 0:
        remainder //= 2
        power += 1
    for _ in range(rounds):
        base = secrets.randbelow(candidate - 3) + 2
        value = pow(base, remainder, candidate)
        if value in (1, candidate - 1):
            continue
        for _ in range(power - 1):
            value = value * value % candidate
            if value == candidate - 1:
                break
        else:
            return False
    return True


def generate_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if candidate % PUBLIC_EXPONENT != 1 and is_probable_prime(candidate):
            return candidate


def generate_keypair(bits: int = DEFAULT_BITS) -> tuple[int, int]:
    """Return (modulus, private_exponent) for a fresh keypair."""
    half = bits // 2
    while True:
        p = generate_prime(half)
        q = generate_prime(half)
        if p == q:
            continue
        modulus = p * q
        if modulus.bit_length() != bits:
            continue
        try:
            private_exponent = pow(PUBLIC_EXPONENT, -1, (p - 1) * (q - 1))
        except ValueError:
            continue
        probe = secrets.randbelow(modulus)
        if pow(pow(probe, private_exponent, modulus), PUBLIC_EXPONENT, modulus) != probe:
            continue
        return modulus, private_exponent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path, help="Where to write the private key JSON")
    parser.add_argument("--bits", type=int, default=DEFAULT_BITS, help=f"Modulus size (default {DEFAULT_BITS})")
    args = parser.parse_args()

    if args.bits < 2048:
        parser.error("refusing to generate a key smaller than 2048 bits")
    if args.output.exists():
        parser.error(f"{args.output} already exists; move it aside before generating a new key")

    modulus, private_exponent = generate_keypair(args.bits)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"n": str(modulus), "d": str(private_exponent)}, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Private key written to {args.output}")
    print(f"Modulus is {modulus.bit_length()} bits. Embed this public half in src/licensing.py:")
    print()
    print(f'    "{modulus}"')
    print()
    print("Keep the private key off version control and back it up before using it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
