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

# Public half of the online license service key. The service issues licenses
# automatically after a Stripe purchase and holds the matching private half; the
# owner key above stays offline. Keeping them separate means a compromised
# server costs one revocable key instead of the offline root of trust. Set to
# None until a service key is deployed.
SERVICE_PUBLIC_KEY_N = int(
    "17658911817149879548257414856825709742103971762945834039622974386111895871870547769377889674523578834865437139275329548507282479930879497850192434393255568568784314250680109668519484589220605899721056990617194933656549574485072711761994956534038466081606755279947126938592680796323235661708541270156959796416241970594013314552969136088030245078543107456245641083635172685785510790775089701495382478834497904223820508542556972479651531682821305298949772900532452420549368168197452871395388495967137341910117798280064217261469533058576848578324563025090961000379246010816499600471083778126531243967299398055793484406371"
)
SERVICE_PUBLIC_KEY_E = 65537

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
    """Accept a signature from the offline owner key or the license service key.

    Both are trusted to issue paid licenses. They are separate keys so the
    service key can be rotated on its own if the server is ever compromised,
    without invalidating licenses signed offline.
    """
    if _rsa_verify_with_key(message, signature, PUBLIC_KEY_N, PUBLIC_KEY_E):
        return True
    if SERVICE_PUBLIC_KEY_N is None:
        return False
    return _rsa_verify_with_key(message, signature, SERVICE_PUBLIC_KEY_N, SERVICE_PUBLIC_KEY_E)


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
            "intro": "Zadejte e-mailovou adresu, se kterou jste LongJumpReplay koupili. Pošleme na ni ověřovací kód.",
            "email": "E-mailová adresa z nákupu",
            "send": "Poslat ověřovací kód",
            "code": "Ověřovací kód z e-mailu",
            "activate": "Aktivovat tento počítač",
            "code_sent": "Kód jsme poslali na {email}. Platí {minutes} minut. Zkontrolujte i složku se spamem.",
            "activated": "Hotovo. Tento počítač je aktivovaný.",
            "working": "Pracuji…",
            "start": "Spustit testování na 72 hodin",
            "continue": "Pokračovat v testování",
            "cancel": "Ukončit",
            "active": "Testování je aktivní do {expiry}. Zbývá exportů: {remaining}.",
            "legacy": "Mám starší licenční klíč",
            "legacy_title": "Aktivace licenčním klíčem",
            "machine": "Kód počítače",
            "key": "Licenční klíč",
            "key_activate": "Aktivovat klíčem",
            "back": "Zpět",
            "need_email": "Zadejte prosím platnou e-mailovou adresu.",
            "need_code": "Zadejte šestimístný kód z e-mailu.",
            "no_active_license": "E-mail byl ověřen, ale k tomuto účtu není přiřazeno aktivní předplatné ani doživotní licence.",
        }
    return {
        "title": "Activate LongJumpReplay",
        "intro": "Enter the email address you bought LongJumpReplay with. We will send a verification code to it.",
        "email": "Purchase email address",
        "send": "Send verification code",
        "code": "Verification code from the email",
        "activate": "Activate this computer",
        "code_sent": "Code sent to {email}. It is valid for {minutes} minutes. Check your spam folder too.",
        "activated": "Done. This computer is activated.",
        "working": "Working…",
        "start": "Start 72-hour trial",
        "continue": "Continue trial",
        "cancel": "Exit",
        "active": "Trial active until {expiry}. Exports remaining: {remaining}.",
        "legacy": "I have an older license key",
        "legacy_title": "Activate with a license key",
        "machine": "Machine code",
        "key": "License key",
        "key_activate": "Activate with key",
        "back": "Back",
        "need_email": "Please enter a valid email address.",
        "need_code": "Enter the six-digit code from the email.",
        "no_active_license": "Email verified, but this account has no active subscription or lifetime licence.",
    }


def ensure_license_or_trial(
    root: tk.Tk,
    language: str,
    startup_check: object | None = None,
) -> bool:
    """Show paid activation or the free-trial choice before a frozen launch.

    Activation is email-first: the customer enters the address they bought with,
    receives a code, and this computer is registered against their licence. A
    previously issued machine-bound key still works, behind a secondary link, so
    existing customers are not stranded.
    """
    from . import activation as activation_api
    from .authorization import clear_authorization

    # Normal startup supplies the visible every-launch check. Direct callers
    # use the same policy so a valid plan is never skipped silently.
    check = startup_check or activation_api.check_startup_authorization()
    if isinstance(check, activation_api.StartupAuthorizationCheck) and check.allowed:
        return True

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

    if status.active:
        expiry = datetime.fromtimestamp(status.expires_at or 0).astimezone().strftime("%Y-%m-%d %H:%M")
        ttk.Label(body, text=copy["active"].format(expiry=expiry, remaining=status.exports_remaining), wraplength=560, justify="left").pack(anchor="w", pady=(0, 12))

    ttk.Label(body, text=copy["email"], style="Heading.TLabel").pack(anchor="w")
    email_var = tk.StringVar()
    email_entry = ttk.Entry(body, textvariable=email_var, width=54)
    email_entry.pack(fill="x", pady=(4, 8))

    code_frame = ttk.Frame(body)
    ttk.Label(code_frame, text=copy["code"], style="Heading.TLabel").pack(anchor="w")
    code_var = tk.StringVar()
    code_entry = ttk.Entry(code_frame, textvariable=code_var, width=16)
    code_entry.pack(anchor="w", pady=(4, 4))
    code_actions = ttk.Frame(code_frame)
    code_actions.pack(fill="x", pady=(8, 0))

    status_label = ttk.Label(body, text="", wraplength=560, justify="left")
    status_label.pack(anchor="w", pady=(10, 12))
    buttons = ttk.Frame(body)
    buttons.pack(fill="x")

    def fit_dialog_to_content() -> None:
        """Resize after switching steps so newly packed controls cannot be clipped."""
        dialog.update_idletasks()
        width = max(dialog.winfo_width(), dialog.winfo_reqwidth())
        height = dialog.winfo_reqheight()
        screen_width, screen_height = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def busy(text: str) -> None:
        status_label.configure(text=text)
        dialog.update_idletasks()

    def send_code() -> None:
        email = email_var.get().strip()
        if "@" not in email or "." not in email.split("@")[-1]:
            status_label.configure(text=copy["need_email"])
            return
        busy(copy["working"])
        try:
            minutes = activation_api.request_code(email)
        except activation_api.ActivationError as error:
            message = copy["no_active_license"] if error.code in {"no_license", "license_inactive"} else str(error)
            status_label.configure(text=message)
            return
        code_frame.pack(anchor="w", fill="x", before=status_label)
        send_button.pack_forget()
        code_entry.focus_set()
        status_label.configure(text=copy["code_sent"].format(email=email, minutes=minutes))
        fit_dialog_to_content()

    def back_to_email() -> None:
        code_var.set("")
        code_frame.pack_forget()
        status_label.configure(text="")
        if not send_button.winfo_manager():
            send_button.pack(side="right", padx=(0, 8))
        email_entry.focus_set()
        fit_dialog_to_content()

    def do_activate() -> None:
        nonlocal accepted
        code = code_var.get().strip()
        if not code.isdigit() or len(code) != 6:
            status_label.configure(text=copy["need_code"])
            return
        busy(copy["working"])
        try:
            grant = activation_api.verify_code(email_var.get().strip(), code)
            activation_api.activate(grant)
        except activation_api.ActivationError as error:
            message = copy["no_active_license"] if error.code in {"no_license", "license_inactive"} else str(error)
            status_label.configure(text=message)
            return
        status_label.configure(text=copy["activated"])
        accepted = True
        dialog.destroy()

    def show_legacy() -> None:
        """The previous machine-bound key flow, kept for existing customers."""
        legacy = tk.Toplevel(dialog)
        legacy.title(copy["legacy_title"])
        legacy.resizable(False, False)
        legacy.grab_set()
        pane = ttk.Frame(legacy, padding=20)
        pane.pack(fill="both", expand=True)
        ttk.Label(pane, text=copy["machine"], style="Heading.TLabel").pack(anchor="w")
        machine_entry = ttk.Entry(pane, width=30)
        machine_entry.insert(0, machine_code())
        machine_entry.configure(state="readonly")
        machine_entry.pack(anchor="w", pady=(4, 12))
        ttk.Label(pane, text=copy["key"], style="Heading.TLabel").pack(anchor="w")
        key_var = tk.StringVar()
        ttk.Entry(pane, textvariable=key_var, width=70).pack(fill="x", pady=(4, 10))
        legacy_status = ttk.Label(pane, text="", wraplength=520, justify="left")
        legacy_status.pack(anchor="w", pady=(6, 10))
        row = ttk.Frame(pane)
        row.pack(fill="x")

        def use_key() -> None:
            nonlocal accepted
            valid, reason, _ = verify_license(key_var.get(), machine_code())
            if not valid:
                legacy_status.configure(text=Translator(language)(reason))
                return
            _save_license(key_var.get())
            # A machine-bound key supersedes any stale server authorization.
            clear_authorization()
            accepted = True
            legacy.destroy()
            dialog.destroy()

        ttk.Button(row, text=copy["back"], command=legacy.destroy).pack(side="right")
        ttk.Button(row, text=copy["key_activate"], command=use_key, style="Accent.TButton").pack(side="right", padx=(0, 8))
        legacy.bind("<Return>", lambda _event: use_key())

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

    ttk.Button(code_actions, text=copy["back"], command=back_to_email).pack(side="left")
    ttk.Button(code_actions, text=copy["activate"], command=do_activate, style="Accent.TButton").pack(side="right")

    ttk.Button(buttons, text=copy["cancel"], command=cancel).pack(side="right")
    if status.active:
        ttk.Button(buttons, text=copy["continue"], command=continue_trial).pack(side="right", padx=(0, 8))
    else:
        ttk.Button(buttons, text=copy["start"], command=begin_trial).pack(side="right", padx=(0, 8))
    # The email step owns the Send action. Once the code arrives, the code
    # section exposes explicit Back and Activate controls instead of silently
    # repurposing the button at the bottom of the dialog.
    send_button = ttk.Button(buttons, text=copy["send"], command=send_code, style="Accent.TButton")
    send_button.pack(side="right", padx=(0, 8))
    ttk.Button(buttons, text=copy["legacy"], command=show_legacy).pack(side="left")
    dialog.protocol("WM_DELETE_WINDOW", cancel)

    def on_return(_event: object) -> None:
        # Enter advances whichever step is on screen.
        if code_frame.winfo_ismapped():
            do_activate()
        else:
            send_code()

    dialog.bind("<Return>", on_return)
    email_entry.focus_set()
    fit_dialog_to_content()
    dialog.deiconify(); dialog.lift(); dialog.focus_force()
    root.wait_window(dialog)
    return accepted
