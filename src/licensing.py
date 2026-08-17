from __future__ import annotations

import base64
import binascii
from datetime import datetime
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
# Version 2 keys were issued by the previous 3.1 release despite the product
# now being version 3. Keep accepting them while new keys use version 3.
SUPPORTED_MAJOR_VERSION = "3"
SUPPORTED_PAID_MAJOR_VERSIONS = frozenset({"2", "3"})

# Public half of the offline signing key. The private half stays in the local
# license-admin tool and is never imported by the application.
PUBLIC_KEY_N = int(
    "23989320552588945571111398601861920915476518414796272647456638076716879240395997329768144404011967653561280854212024905459558623501670928429408001272051662728798081445675404375232191797893905295078437872606138323856818241191927993853266489309008710524218224766891401112534071657687619315762459395425031265768043439111940589144695017799973333154805295506094325076417530971618703203219145102113019612485855533437016421568209267220233690643232509893065756504791671230323032822015040342592372252579927732572627094048111194834672155554306832314283132454653217483057069969093299457452165682336557289874443214381329775208449"
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


def _rsa_verify_with_key(message: bytes, signature: bytes, modulus: int, exponent: int = PUBLIC_KEY_E) -> bool:
    size = (modulus.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    encoded = pow(int.from_bytes(signature, "big"), exponent, modulus).to_bytes(size, "big")
    return encoded == _encoded_message(message, size)


def _rsa_verify(message: bytes, signature: bytes) -> bool:
    return _rsa_verify_with_key(message, signature, PUBLIC_KEY_N, PUBLIC_KEY_E)


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
        if str(payload.get("major_version")) not in SUPPORTED_PAID_MAJOR_VERSIONS:
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


def _trial_copy(language: str) -> dict[str, str]:
    if language == "cs":
        return {
            "title": "Aktivace LongJumpReplay",
            "intro": "Aktivujte placenou licenci, nebo spusťte bezplatné testování na 72 hodin.",
            "machine": "Kód počítače",
            "key": "Licenční klíč",
            "activate": "Aktivovat licenci",
            "start": "Spustit testování na 72 hodin",
            "continue": "Pokračovat v testování",
            "cancel": "Ukončit",
            "active": "Testování je aktivní do {expiry}. Zbývá exportů: {remaining}.",
        }
    return {
        "title": "Activate LongJumpReplay",
        "intro": "Activate a paid license, or start a free 72-hour evaluation.",
        "machine": "Machine code",
        "key": "License key",
        "activate": "Activate license",
        "start": "Start 72-hour trial",
        "continue": "Continue trial",
        "cancel": "Exit",
        "active": "Trial active until {expiry}. Exports remaining: {remaining}.",
    }


def ensure_license_or_trial(root: tk.Tk, language: str) -> bool:
    """Show paid activation or the free-trial choice before a frozen launch."""
    paid_valid, _, _ = load_saved_license()
    if paid_valid:
        return True
    from .trial import refresh_trial_status, start_local_trial, trial_status

    copy = _trial_copy(language)
    status = refresh_trial_status()
    accepted = False
    dialog = tk.Toplevel(root)
    dialog.title(copy["title"])
    dialog.resizable(False, False)
    dialog.grab_set()
    body = ttk.Frame(dialog, padding=22)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=copy["title"], style="Title.TLabel").pack(anchor="w")
    ttk.Label(body, text=copy["intro"], wraplength=560, justify="left").pack(anchor="w", pady=(8, 16))
    ttk.Label(body, text=copy["machine"], style="Heading.TLabel").pack(anchor="w")
    machine_entry = ttk.Entry(body, width=30)
    machine_entry.insert(0, machine_code())
    machine_entry.configure(state="readonly")
    machine_entry.pack(anchor="w", pady=(4, 12))
    if status.active:
        expiry = datetime.fromtimestamp(status.expires_at or 0).astimezone().strftime("%Y-%m-%d %H:%M")
        ttk.Label(body, text=copy["active"].format(expiry=expiry, remaining=status.exports_remaining), wraplength=560, justify="left").pack(anchor="w", pady=(0, 12))
    ttk.Label(body, text=copy["key"], style="Heading.TLabel").pack(anchor="w")
    key_var = tk.StringVar()
    ttk.Entry(body, textvariable=key_var, width=70).pack(fill="x", pady=(4, 10))
    status_label = ttk.Label(body, text="", wraplength=560, justify="left")
    status_label.pack(anchor="w", pady=(10, 12))
    buttons = ttk.Frame(body)
    buttons.pack(fill="x")

    def activate() -> None:
        nonlocal accepted
        valid, reason, _ = verify_license(key_var.get(), machine_code())
        if not valid:
            status_label.configure(text=Translator(language)(reason))
            return
        _save_license(key_var.get())
        accepted = True
        dialog.destroy()

    def begin_trial() -> None:
        nonlocal accepted
        try:
            trial_status_after = start_local_trial()
        except Exception as exc:
            status_label.configure(text=str(exc))
            return
        if not trial_status_after.active:
            status_label.configure(text="The trial service returned an inactive trial.")
            return
        accepted = True
        dialog.destroy()

    def continue_trial() -> None:
        nonlocal accepted
        if trial_status().active:
            accepted = True
            dialog.destroy()
        else:
            status_label.configure(text="The trial has expired or is no longer valid.")

    def cancel() -> None:
        dialog.destroy()

    ttk.Button(buttons, text=copy["cancel"], command=cancel).pack(side="right")
    if status.active:
        ttk.Button(buttons, text=copy["continue"], command=continue_trial, style="Accent.TButton").pack(side="right", padx=(0, 8))
    else:
        ttk.Button(buttons, text=copy["start"], command=begin_trial, style="Accent.TButton").pack(side="right", padx=(0, 8))
    ttk.Button(buttons, text=copy["activate"], command=activate).pack(side="right", padx=(0, 8))
    dialog.protocol("WM_DELETE_WINDOW", cancel)
    dialog.bind("<Return>", lambda _event: activate())
    dialog.update_idletasks()
    width, height = dialog.winfo_width(), dialog.winfo_height()
    screen_width, screen_height = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
    dialog.geometry(f"{width}x{height}+{max(0, (screen_width - width) // 2)}+{max(0, (screen_height - height) // 2)}")
    dialog.deiconify(); dialog.lift(); dialog.focus_force()
    root.wait_window(dialog)
    return accepted
