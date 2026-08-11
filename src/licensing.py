from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import platform
import tkinter as tk
from tkinter import ttk
import uuid

from .i18n import Translator
from .portable_paths import writable_data_directory


PRODUCT_ID = "LongJumpReplay"
SUPPORTED_MAJOR_VERSION = "2"

# Public half of the offline signing key. The private half stays in the local
# license-admin tool and is never imported by the application.
PUBLIC_KEY_N = int(
    "64096297099353406280641690278502117868576339283076304189541373730379189432764838042170623255586343772713946519290710125199265601846979684281949346516332470454941132989256874167725319196886861896853313777297029909671948064773596113015831386254748826318511102466121842017122518967542744551260639429681720870457"
)
PUBLIC_KEY_E = 65537
_SHA256_DER_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical_payload(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _encoded_message(message: bytes, size: int) -> bytes:
    digest_info = _SHA256_DER_PREFIX + hashlib.sha256(message).digest()
    if size < len(digest_info) + 11:
        raise ValueError("RSA key is too small for SHA-256")
    return b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info


def _rsa_verify(message: bytes, signature: bytes) -> bool:
    size = (PUBLIC_KEY_N.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    encoded = pow(int.from_bytes(signature, "big"), PUBLIC_KEY_E, PUBLIC_KEY_N).to_bytes(size, "big")
    return encoded == _encoded_message(message, size)


def machine_code() -> str:
    """Return a stable, non-secret identifier for this computer."""
    values = [platform.system(), platform.node(), os.environ.get("COMPUTERNAME", ""), str(uuid.getnode())]
    digest = hashlib.sha256("|".join(values).encode("utf-8")).hexdigest().upper()
    return "-".join(digest[index : index + 4] for index in range(0, 16, 4))


def license_path() -> Path:
    return writable_data_directory() / "license.json"


def encode_license(payload: dict[str, object], signature: bytes) -> str:
    return f"LJR2.{_urlsafe_encode(canonical_payload(payload))}.{_urlsafe_encode(signature)}"


def verify_license(key: str, expected_machine: str | None = None) -> tuple[bool, str, dict[str, object] | None]:
    try:
        prefix, encoded_payload, encoded_signature = key.strip().split(".", 2)
        if prefix != "LJR2":
            return False, "license.invalid_format", None
        payload = json.loads(_urlsafe_decode(encoded_payload).decode("utf-8"))
        if not isinstance(payload, dict):
            return False, "license.invalid_format", None
        if not _rsa_verify(canonical_payload(payload), _urlsafe_decode(encoded_signature)):
            return False, "license.invalid_signature", None
        if payload.get("product") != PRODUCT_ID:
            return False, "license.wrong_product", None
        if str(payload.get("major_version")) != SUPPORTED_MAJOR_VERSION:
            return False, "license.wrong_version", None
        if expected_machine and payload.get("machine_code") != expected_machine:
            return False, "license.wrong_machine", None
        return True, "license.accepted", payload
    except (ValueError, TypeError, UnicodeError, binascii.Error, json.JSONDecodeError):
        return False, "license.invalid_format", None


def load_saved_license() -> tuple[bool, str, dict[str, object] | None]:
    try:
        return verify_license(license_path().read_text(encoding="utf-8"), machine_code())
    except OSError:
        return False, "license.missing", None


def _save_license(key: str) -> None:
    path = license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(key.strip() + "\n", encoding="utf-8")
    temporary.replace(path)


def ensure_license(root: tk.Tk, language: str) -> bool:
    valid, _, _ = load_saved_license()
    if valid:
        return True
    translator = Translator(language)
    accepted = False
    dialog = tk.Toplevel(root)
    dialog.title(translator("license.title"))
    dialog.resizable(False, False)
    dialog.grab_set()
    body = ttk.Frame(dialog, padding=22)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=translator("license.heading"), style="Title.TLabel").pack(anchor="w")
    ttk.Label(body, text=translator("license.intro"), wraplength=520, justify="left").pack(anchor="w", pady=(8, 16))
    ttk.Label(body, text=translator("license.machine_code"), style="Heading.TLabel").pack(anchor="w")
    machine = ttk.Entry(body, width=30)
    machine.insert(0, machine_code())
    machine.configure(state="readonly")
    machine.pack(anchor="w", pady=(4, 3))
    ttk.Label(body, text=translator("license.machine_help"), wraplength=520, justify="left").pack(anchor="w", pady=(0, 14))
    ttk.Label(body, text=translator("license.key_label"), style="Heading.TLabel").pack(anchor="w")
    key_var = tk.StringVar()
    key_entry = ttk.Entry(body, textvariable=key_var, width=70)
    key_entry.pack(fill="x", pady=(4, 5))
    status = ttk.Label(body, text="", wraplength=520, justify="left")
    status.pack(anchor="w", pady=(0, 12))
    buttons = ttk.Frame(body)
    buttons.pack(fill="x")

    def activate() -> None:
        nonlocal accepted
        valid, reason, _ = verify_license(key_var.get(), machine_code())
        if not valid:
            status.configure(text=translator(reason))
            return
        _save_license(key_var.get())
        accepted = True
        dialog.destroy()

    def cancel() -> None:
        dialog.destroy()

    ttk.Button(buttons, text=translator("license.cancel"), command=cancel).pack(side="right")
    ttk.Button(buttons, text=translator("license.activate"), command=activate, style="Accent.TButton").pack(side="right", padx=(0, 8))
    dialog.protocol("WM_DELETE_WINDOW", cancel)
    dialog.bind("<Return>", lambda _event: activate())
    # The application root is intentionally withdrawn before this dialog is
    # shown.  On Windows, making the dialog transient to that hidden root can
    # leave the activation window owned but invisible while the process waits
    # in wait_window().  Center and explicitly raise an independent dialog so
    # first-run EXE launches always present the activation UI.
    dialog.update_idletasks()
    width, height = dialog.winfo_width(), dialog.winfo_height()
    screen_width, screen_height = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
    dialog.geometry(f"{width}x{height}+{max(0, (screen_width - width) // 2)}+{max(0, (screen_height - height) // 2)}")
    dialog.deiconify()
    dialog.lift()
    try:
        dialog.attributes("-topmost", True)
    except tk.TclError:
        pass
    dialog.focus_force()
    key_entry.focus_set()
    root.wait_window(dialog)
    return accepted
