from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from datetime import datetime
import hashlib
import json
import os
import platform
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
import uuid
import webbrowser

try:
    import qrcode
except ImportError:  # pragma: no cover - the packaged build includes qrcode
    qrcode = None

from PIL import ImageTk

from .theme import center_popup


def _run_background(
    window: tk.Misc,
    task: Callable[[], object],
    on_success: Callable[[object], None],
    on_error: Callable[[object], None],
) -> None:
    """Run blocking activation I/O without freezing Tk's animation loop."""
    results: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            results.put((True, task()))
        except Exception as error:
            results.put((False, error))

    def poll() -> None:
        try:
            succeeded, value = results.get_nowait()
        except queue.Empty:
            try:
                if window.winfo_exists():
                    window.after(15, poll)
            except tk.TclError:
                pass
            return
        try:
            if not window.winfo_exists():
                return
        except tk.TclError:
            return
        if succeeded:
            on_success(value)
        else:
            on_error(value)

    threading.Thread(target=worker, name="activation-request", daemon=True).start()
    window.after(15, poll)

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


def format_verification_code_input(value: str) -> str:
    """Keep pasted or typed activation codes to six ASCII digits."""
    return "".join(character for character in value if character in "0123456789")[:6]


def format_activation_key_input(value: str) -> str:
    """Format a portal key as 4-4-4 while the customer types or pastes."""
    compact = ""
    for character in value.upper():
        if len(compact) < 4:
            allowed = "0123456789"
        elif len(compact) < 8:
            allowed = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        else:
            allowed = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        if character in allowed:
            compact += character
        if len(compact) == 12:
            break
    formatted = "-".join(compact[index:index + 4] for index in range(0, len(compact), 4))
    # Draw the separator as soon as a group is complete. Waiting for the next
    # character makes the field feel delayed and causes Tk to place that next
    # character on the wrong side of a newly inserted separator.
    if len(compact) in {4, 8}:
        formatted += "-"
    return formatted


def create_pairing_qr(url: str):
    """Create an in-memory QR image for a short-lived portal pairing URL."""
    if qrcode is None:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=3,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def _activation_copy(language: str) -> dict[str, str]:
    if language == "cs":
        return {
            "pair_code": "Párovací kód", "pair_link": "Odkaz portálu", "pair_scan": "Naskenujte QR kód pro otevření párování", "pair_expires": "Platí ještě {seconds} s.", "pair_expired": "Párování vypršelo. Zavřete toto okno a začněte znovu.", "pair_qr_unavailable": "QR kód není v tomto prostředí dostupný. Použijte odkaz nebo šestimístný kód.",
            "title": "Aktivace LongJumpReplay", "intro": "Aktivujte počítač e-mailem použitým při nákupu. Pošleme vám šestimístný ověřovací kód.",
            "email": "E-mail z nákupu", "send": "Poslat ověřovací kód", "code": "Ověřovací kód z e-mailu",
            "activate": "Aktivovat tento počítač", "code_sent": "Kód byl odeslán na {email}. Platí {minutes} minut. Zkontrolujte také spam.",
            "activated": "Hotovo. Tento počítač je aktivován.", "working": "Pracuji…", "start": "Spustit 72hodinové hodnocení",
            "continue": "Pokračovat v hodnocení", "cancel": "Ukončit", "active": "Hodnocení je aktivní do {expiry}. Zbývají {remaining} exporty.",
            "alternate": "Aktivovat pomocí klíče", "pair": "Spárovat přes zákaznický portál", "pair_title": "Spárovat tento počítač", "pair_hint": "Otevřete odkaz v zákaznickém portálu nebo zadejte šestimístný kód. Po schválení se počítač aktivuje automaticky.", "pair_open": "Otevřít portál", "pair_copy": "Kopírovat kód", "pair_waiting": "Čekám na schválení…", "pair_done": "Hotovo. Tento počítač je aktivován.",
            "key_title": "Aktivační klíč z portálu", "key": "Aktivační klíč",
            "key_hint": "Klíč ve formátu 0000-ABCD-2EFG najdete ve svém zákaznickém účtu.", "key_activate": "Aktivovat tento počítač",
            "back": "Zpět", "need_email": "Zadejte platnou e-mailovou adresu.", "need_code": "Zadejte šestimístný kód z e-mailu.",
            "need_key": "Zadejte platný aktivační klíč.", "buy": "Koupit licenci na tomaspisar.cz",
            "licence_actions": "Aktivace licence", "evaluation_actions": "Zkušební režim",
            "trial_limits": "72hodinové hodnocení slouží pro kameru, zmrazení a přehrávání. Soutěžní režim, rozhodování, výsledky a důkazní balíčky jsou vypnuté. Zahrnuje 3 samostatné exporty videa.",
            "no_active_license": "E-mail byl ověřen, ale tento účet nemá zakoupenou aktivní licenci. Licenci můžete koupit na tomaspisar.cz.",
        }
    return {
        "pair_code": "Pairing code", "pair_link": "Portal link", "pair_scan": "Scan the QR code to open pairing", "pair_expires": "Expires in {seconds}s.", "pair_expired": "Pairing expired. Close this window and start again.", "pair_qr_unavailable": "QR rendering is unavailable in this environment. Use the link or six-digit code.",
        "title": "Activate LongJumpReplay", "intro": "Activate this computer with the email address used for your purchase. We will send a six-digit verification code.",
        "email": "Purchase email", "send": "Send verification code", "code": "Verification code from email",
        "activate": "Activate this computer", "code_sent": "Code sent to {email}. It is valid for {minutes} minutes. Check spam too.",
        "activated": "Done. This computer is activated.", "working": "Working…", "start": "Start 72-hour evaluation",
        "continue": "Continue evaluation", "cancel": "Exit", "active": "Evaluation active until {expiry}. Exports remaining: {remaining}.",
         "alternate": "Activate with a key", "pair": "Pair from customer portal", "pair_title": "Pair this computer", "pair_hint": "Open the link in your customer portal or enter the six-digit code. After approval, this computer activates automatically.", "pair_open": "Open portal", "pair_copy": "Copy code", "pair_waiting": "Waiting for approval…", "pair_done": "Done. This computer is activated.",
         "key_title": "Portal activation key", "key": "Activation key",
        "key_hint": "Find the 0000-ABCD-2EFG key in your customer account.", "key_activate": "Activate this computer",
        "back": "Back", "need_email": "Enter a valid email address.", "need_code": "Enter the six-digit code from the email.",
        "need_key": "Enter a valid activation key.", "buy": "Buy a licence at tomaspisar.cz",
        "licence_actions": "Licence activation", "evaluation_actions": "Evaluation mode",
        "trial_limits": "The 72-hour evaluation demonstrates camera capture, freeze and replay. Competition setup, judging, results and evidence packages are disabled. Three standalone video exports are included.",
        "no_active_license": "Email verified, but this account has no purchased active licence. Buy one at tomaspisar.cz.",
    }


# Kept as an internal compatibility name for the GUI test harness and any
# downstream skinning integrations. It now returns only the redesigned flow.
_trial_copy = _activation_copy


def ensure_license_or_trial(
    root: tk.Tk,
    language: str,
    startup_check: object | None = None,
) -> bool:
    """Show paid activation or the free-trial choice before a frozen launch.

    Activation is email-first: the customer enters the address they bought with,
    receives a code, and this computer is registered against their licence. The
    reusable portal key is the only alternative; the retired offline machine-key
    flow is not loaded or accepted by the customer startup path.
    """
    from . import activation as activation_api

    # Normal startup supplies the visible every-launch check. Direct callers
    # use the same policy so a valid plan is never skipped silently.
    check = startup_check or activation_api.check_startup_authorization()
    if isinstance(check, activation_api.StartupAuthorizationCheck) and check.allowed:
        return True

    from .trial import refresh_trial_status, start_local_trial, trial_status

    copy = _activation_copy(language)
    status = refresh_trial_status()
    accepted = False
    dialog = tk.Toplevel(root)
    center_popup(dialog)
    dialog.title(copy["title"])
    dialog.resizable(False, False)
    dialog.minsize(680, 0)
    dialog.grab_set()
    body = ttk.Frame(dialog, padding=22)
    body.pack(fill="both", expand=True)
    hero = tk.Frame(body, bg="#101a20", padx=18, pady=16)
    hero.pack(fill="x", pady=(0, 14))
    tk.Label(hero, text="LONGJUMPREPLAY", bg="#101a20", fg="#62d9c6", font=("Segoe UI Semibold", 10)).pack(anchor="w")
    tk.Label(hero, text=copy["title"], bg="#101a20", fg="#f4f7f8", font=("Segoe UI Semibold", 22)).pack(anchor="w", pady=(3, 0))
    ttk.Label(body, text=copy["intro"], wraplength=560, justify="left").pack(anchor="w", pady=(8, 16))

    if status.active:
        expiry = datetime.fromtimestamp(status.expires_at or 0).astimezone().strftime("%Y-%m-%d %H:%M")
        ttk.Label(body, text=copy["active"].format(expiry=expiry, remaining=status.exports_remaining), wraplength=560, justify="left").pack(anchor="w", pady=(0, 12))

    ttk.Label(body, text="1  " + copy["email"], style="Heading.TLabel").pack(anchor="w")
    email_var = tk.StringVar()
    email_entry = ttk.Entry(body, textvariable=email_var, width=54)
    email_entry.pack(fill="x", pady=(4, 8))

    code_frame = ttk.Frame(body)
    ttk.Label(code_frame, text="2  " + copy["code"], style="Heading.TLabel").pack(anchor="w")
    code_var = tk.StringVar()
    code_entry = ttk.Entry(code_frame, textvariable=code_var, width=16)
    code_entry.pack(anchor="w", pady=(4, 4))

    def format_code_input(*_args: object) -> None:
        formatted = format_verification_code_input(code_var.get())
        if formatted != code_var.get():
            code_var.set(formatted)

    code_var.trace_add("write", format_code_input)
    code_actions = ttk.Frame(code_frame)
    code_actions.pack(fill="x", pady=(8, 0))

    status_label = ttk.Label(body, text="", wraplength=560, justify="left")
    status_label.pack(anchor="w", pady=(10, 12))
    progress_bar = ttk.Progressbar(body, mode="indeterminate", style="Modal.Horizontal.TProgressbar")
    licence_actions = ttk.LabelFrame(body, text=copy["licence_actions"], padding=12)
    licence_actions.pack(fill="x", pady=(0, 12))
    licence_buttons = ttk.Frame(licence_actions)
    licence_buttons.pack(fill="x")
    licence_buttons.columnconfigure((0, 1), weight=1, uniform="licence-action")
    evaluation_actions = ttk.LabelFrame(body, text=copy["evaluation_actions"], padding=12)
    evaluation_actions.pack(fill="x", pady=(0, 12))
    evaluation_actions.columnconfigure(0, weight=1)
    footer_actions = ttk.Frame(body)
    footer_actions.pack(fill="x")
    request_in_progress = False

    def fit_dialog_to_content() -> None:
        """Resize after switching steps so newly packed controls cannot be clipped."""
        dialog.update_idletasks()
        width = max(dialog.winfo_width(), dialog.winfo_reqwidth())
        height = dialog.winfo_reqheight()
        screen_width, screen_height = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def busy(text: str, *buttons: ttk.Button) -> bool:
        nonlocal request_in_progress
        if request_in_progress:
            return False
        request_in_progress = True
        status_label.configure(text=text)
        for button in buttons:
            button.state(["disabled"])
        if not progress_bar.winfo_manager():
            progress_bar.pack(fill="x", pady=(0, 12), before=licence_actions)
        progress_bar.start(12)
        return True

    def stop_busy(*buttons: ttk.Button) -> None:
        nonlocal request_in_progress
        request_in_progress = False
        progress_bar.stop()
        progress_bar.pack_forget()
        for button in buttons:
            button.state(["!disabled"])

    def send_code() -> None:
        email = email_var.get().strip()
        if "@" not in email or "." not in email.split("@")[-1]:
            status_label.configure(text=copy["need_email"])
            return
        if not busy(copy["working"], send_button):
            return

        def failed(error: object) -> None:
            stop_busy(send_button)
            error_code = getattr(error, "code", None)
            message = copy["no_active_license"] if error_code in {"no_license", "license_inactive"} else str(error)
            status_label.configure(text=message)

        def succeeded(minutes: object) -> None:
            stop_busy(send_button)
            code_frame.pack(anchor="w", fill="x", before=status_label)
            send_button.grid_remove()
            code_entry.focus_set()
            status_label.configure(text=copy["code_sent"].format(email=email, minutes=minutes))
            fit_dialog_to_content()

        _run_background(dialog, lambda: activation_api.request_code(email), succeeded, failed)

    def back_to_email() -> None:
        code_var.set("")
        code_frame.pack_forget()
        status_label.configure(text="")
        if not send_button.winfo_manager():
            send_button.grid()
        email_entry.focus_set()
        fit_dialog_to_content()

    def do_activate() -> None:
        nonlocal accepted
        code = code_var.get().strip()
        if not code.isdigit() or len(code) != 6:
            status_label.configure(text=copy["need_code"])
            return
        email = email_var.get().strip()
        if not busy(copy["working"], code_back_button, code_activate_button):
            return

        def activate() -> None:
            grant = activation_api.verify_code(email, code)
            activation_api.activate(grant)

        def failed(error: object) -> None:
            stop_busy(code_back_button, code_activate_button)
            error_code = getattr(error, "code", None)
            message = copy["no_active_license"] if error_code in {"no_license", "license_inactive"} else str(error)
            status_label.configure(text=message)

        def succeeded(_result: object) -> None:
            nonlocal accepted
            stop_busy(code_back_button, code_activate_button)
            status_label.configure(text=copy["activated"])
            accepted = True
            dialog.destroy()

        _run_background(dialog, activate, succeeded, failed)

    def show_pairing() -> None:
        """Pair through the signed-in portal without changing the OTP flow."""
        pair_dialog = tk.Toplevel(dialog)
        center_popup(pair_dialog)
        pair_dialog.title(copy["pair_title"])
        pair_dialog.resizable(False, False)
        pair_dialog.grab_set()
        pane = ttk.Frame(pair_dialog, padding=24)
        pane.pack(fill="both", expand=True)
        ttk.Label(pane, text=copy["pair_title"], style="Title.TLabel").pack(anchor="w")
        ttk.Label(pane, text=copy["pair_hint"], wraplength=520, justify="left").pack(anchor="w", pady=(6, 18))
        pairing_content = ttk.Frame(pane)
        pairing_content.pack(fill="x")
        qr_column = ttk.Frame(pairing_content)
        qr_column.pack(side="left", padx=(0, 18))
        pair_qr = ttk.Label(qr_column, text=copy["working"], anchor="center", width=26)
        pair_qr.pack(pady=(0, 4))
        ttk.Label(qr_column, text=copy["pair_scan"], wraplength=180, justify="center").pack()
        pairing_details = ttk.Frame(pairing_content)
        pairing_details.pack(side="left", fill="both", expand=True)
        ttk.Label(pairing_details, text=copy["pair_code"], style="Heading.TLabel").pack(anchor="w")
        pair_code = tk.StringVar(value="Starting…")
        ttk.Label(pairing_details, textvariable=pair_code, font=("Consolas", 22, "bold")).pack(anchor="w", pady=(4, 10))
        ttk.Label(pairing_details, text=copy["pair_link"], style="Heading.TLabel").pack(anchor="w")
        pair_url = tk.StringVar(value="")
        url_entry = ttk.Entry(pairing_details, textvariable=pair_url, width=48, state="readonly")
        url_entry.pack(fill="x", pady=(4, 10))
        pair_expiry = tk.StringVar(value="")
        ttk.Label(pairing_details, textvariable=pair_expiry).pack(anchor="w")
        pair_status = ttk.Label(pane, text=copy["working"], wraplength=520, justify="left")
        pair_status.pack(anchor="w", pady=(4, 12))
        actions = ttk.Frame(pane)
        actions.pack(fill="x")
        open_button = ttk.Button(actions, text=copy["pair_open"], state="disabled")
        open_button.pack(side="left", fill="x", expand=True, padx=(0, 6))
        copy_button = ttk.Button(actions, text=copy["pair_copy"], state="disabled")
        copy_button.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(actions, text=copy["cancel"], command=pair_dialog.destroy).pack(side="left", fill="x", expand=True, padx=(6, 0))
        pairing_token: str | None = None
        pair_qr_photo = None
        pair_started_at: float | None = None
        pair_expiry_seconds = 600

        def update_expiry() -> None:
            if pair_started_at is None:
                return
            remaining = max(0, int(pair_expiry_seconds - (time.monotonic() - pair_started_at)))
            pair_expiry.set(copy["pair_expires"].format(seconds=remaining))
            if remaining:
                pair_dialog.after(1000, update_expiry)
            else:
                pair_status.configure(text=copy["pair_expired"])

        def copy_pair_code() -> None:
            pair_dialog.clipboard_clear()
            pair_dialog.clipboard_append(pair_code.get())
            pair_status.configure(text=copy["pair_copy"])

        def poll() -> None:
            if not pairing_token:
                return

            def failed(error: object) -> None:
                if getattr(error, "code", None) == "pairing_pending":
                    pair_status.configure(text=copy["pair_waiting"])
                    pair_dialog.after(1800, poll)
                else:
                    pair_status.configure(text=str(error))

            def succeeded(_result: object) -> None:
                nonlocal accepted
                pair_status.configure(text=copy["pair_done"])
                accepted = True
                pair_dialog.after(350, pair_dialog.destroy)
                dialog.after(400, dialog.destroy)

            _run_background(pair_dialog, lambda: activation_api.activate_pairing(pairing_token or ""), succeeded, failed)

        def qr_ready(image: object) -> None:
            nonlocal pair_qr_photo
            if image is None:
                pair_qr.configure(text=copy["pair_qr_unavailable"], image="")
                return
            try:
                pair_qr_photo = ImageTk.PhotoImage(image)
                pair_qr.configure(image=pair_qr_photo, text="")
            except (tk.TclError, TypeError, ValueError):
                pair_qr.configure(text=copy["pair_qr_unavailable"], image="")

        def qr_failed(_error: object) -> None:
            pair_qr.configure(text=copy["pair_qr_unavailable"], image="")

        def pairing_started(value: object) -> None:
            nonlocal pairing_token, pair_started_at, pair_expiry_seconds
            start = value
            pairing_token = start.token
            pair_started_at = time.monotonic()
            pair_expiry_seconds = max(1, int(start.expires_in_seconds))
            pair_code.set(start.code)
            pair_url.set(start.portal_url)
            open_button.configure(state="normal", command=lambda: webbrowser.open(start.portal_url))
            copy_button.configure(state="normal", command=copy_pair_code)
            pair_status.configure(text=copy["pair_waiting"])
            update_expiry()
            _run_background(pair_dialog, lambda: create_pairing_qr(start.portal_url), qr_ready, qr_failed)
            center_popup(pair_dialog, dialog)
            pair_dialog.after(600, poll)

        def pairing_failed(error: object) -> None:
            pair_status.configure(text=str(error))

        _run_background(pair_dialog, activation_api.start_pairing, pairing_started, pairing_failed)
        fit_dialog_to_content()

    def show_key_activation() -> None:
        """Alternative activation using the reusable key from the portal."""
        key_dialog = tk.Toplevel(dialog)
        center_popup(key_dialog)
        key_dialog.title(copy["key_title"])
        key_dialog.resizable(False, False)
        key_dialog.grab_set()
        pane = ttk.Frame(key_dialog, padding=24)
        pane.pack(fill="both", expand=True)
        ttk.Label(pane, text=copy["key_title"], style="Title.TLabel").pack(anchor="w")
        ttk.Label(pane, text=copy["key_hint"], wraplength=520, justify="left").pack(anchor="w", pady=(6, 18))
        ttk.Label(pane, text=copy["key"], style="Heading.TLabel").pack(anchor="w")
        key_var = tk.StringVar()
        key_entry = ttk.Entry(pane, textvariable=key_var, width=32, font=("Consolas", 14))
        key_entry.pack(fill="x", pady=(5, 10))
        key_status = ttk.Label(pane, text="", wraplength=520, justify="left")
        key_status.pack(anchor="w", pady=(6, 10))
        key_progress = ttk.Progressbar(pane, mode="indeterminate", style="Modal.Horizontal.TProgressbar")
        row = ttk.Frame(pane)
        row.pack(fill="x")
        row.columnconfigure((0, 1), weight=1, uniform="key-action")
        key_request_in_progress = False

        format_job: str | None = None
        formatting_key = False

        def apply_key_format() -> None:
            """Apply grouping after Tk finishes the edit, then restore the caret."""
            nonlocal format_job, formatting_key
            format_job = None
            current = key_var.get()
            cursor = key_entry.index(tk.INSERT)
            formatted = format_activation_key_input(current)
            formatted_prefix = format_activation_key_input(current[:cursor])
            if formatted != current:
                formatting_key = True
                key_var.set(formatted)
                formatting_key = False
            key_entry.icursor(min(len(formatted_prefix), len(formatted)))

        def format_key(*_args: object) -> None:
            nonlocal format_job
            if formatting_key or format_job is not None:
                return
            # A StringVar trace fires before Entry completes its cursor update.
            # Formatting on idle gives us the final caret and avoids the
            # one-character jump observed when a dash is inserted.
            format_job = key_dialog.after_idle(apply_key_format)

        key_var.trace_add("write", format_key)

        def use_key() -> None:
            nonlocal key_request_in_progress
            if key_request_in_progress:
                return
            if len(key_var.get()) != 14:
                key_status.configure(text=copy["need_key"])
                return
            key_request_in_progress = True
            key_status.configure(text=copy["working"])
            key_back_button.state(["disabled"])
            key_activate_button.state(["disabled"])
            key_progress.pack(fill="x", pady=(0, 10), before=row)
            key_progress.start(12)

            def failed(error: object) -> None:
                nonlocal key_request_in_progress
                key_request_in_progress = False
                key_progress.stop()
                key_progress.pack_forget()
                key_back_button.state(["!disabled"])
                key_activate_button.state(["!disabled"])
                key_status.configure(text=str(error))

            def succeeded(_result: object) -> None:
                nonlocal accepted
                key_progress.stop()
                accepted = True
                key_dialog.destroy()
                dialog.destroy()

            key = key_var.get()
            _run_background(key_dialog, lambda: activation_api.activate_with_key(key), succeeded, failed)

        key_back_button = ttk.Button(row, text=copy["back"], command=key_dialog.destroy)
        key_back_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        key_activate_button = ttk.Button(row, text=copy["key_activate"], command=use_key, style="Primary.TButton")
        key_activate_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        key_dialog.bind("<Return>", lambda _event: use_key())
        key_entry.focus_set()

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

    code_actions.columnconfigure((0, 1), weight=1, uniform="code-action")
    code_back_button = ttk.Button(code_actions, text=copy["back"], command=back_to_email)
    code_back_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    code_activate_button = ttk.Button(code_actions, text=copy["activate"], command=do_activate, style="Primary.TButton")
    code_activate_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    ttk.Button(footer_actions, text=copy["cancel"], command=cancel).pack(side="right")
    if status.active:
        ttk.Button(evaluation_actions, text=copy["continue"], command=continue_trial, style="Primary.TButton").grid(row=0, column=0, sticky="ew")
    else:
        ttk.Button(evaluation_actions, text=copy["start"], command=begin_trial, style="Primary.TButton").grid(row=0, column=0, sticky="ew")
    # The email step owns the Send action. Once the code arrives, the code
    # section exposes explicit Back and Activate controls instead of silently
    # repurposing the button at the bottom of the dialog.
    send_button = ttk.Button(licence_buttons, text=copy["send"], command=send_code, style="Primary.TButton")
    send_button.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    ttk.Button(licence_buttons, text=copy["alternate"], command=show_key_activation).grid(row=1, column=0, sticky="ew", padx=(0, 6))
    ttk.Button(licence_buttons, text=copy["pair"], command=show_pairing).grid(row=1, column=1, sticky="ew", padx=(6, 0))
    ttk.Button(licence_buttons, text=copy["buy"], command=lambda: webbrowser.open("https://tomaspisar.cz/software/longjumpreplay/#buy")).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    ttk.Separator(body).pack(fill="x", pady=(18, 10))
    ttk.Label(body, text=copy["trial_limits"], wraplength=620, justify="left").pack(anchor="w")
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
