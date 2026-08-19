import tkinter as tk
from tkinter import ttk

from src import activation, licensing, trial


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def test_code_step_has_back_and_activate_actions(monkeypatch):
    monkeypatch.setattr(licensing, "load_saved_license", lambda: (False, "license.missing", None))
    monkeypatch.setattr(activation, "request_code", lambda _email: 10)
    monkeypatch.setattr(
        trial,
        "refresh_trial_status",
        lambda: trial.TrialStatus(False, False, 0, 3, None),
    )

    root = tk.Tk()
    root.withdraw()
    observed = {}

    def drive_dialog():
        dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        email = next(widget for widget in _descendants(dialog) if isinstance(widget, ttk.Entry))
        email.insert(0, "new@example.com")
        send = next(
            widget for widget in _descendants(dialog)
            if isinstance(widget, ttk.Button) and widget.cget("text") == "Send verification code"
        )
        send.invoke()
        dialog.update_idletasks()

        buttons = {
            widget.cget("text"): widget
            for widget in _descendants(dialog)
            if isinstance(widget, ttk.Button)
        }
        observed["activate_visible"] = buttons["Activate this computer"].winfo_ismapped()
        observed["back_visible"] = buttons["Back"].winfo_ismapped()
        observed["send_hidden"] = not send.winfo_manager()

        buttons["Back"].invoke()
        dialog.update_idletasks()
        observed["send_restored"] = bool(send.winfo_manager())
        observed["email_focus_target"] = dialog.focus_get() is email
        dialog.destroy()

    root.after(20, drive_dialog)
    accepted = licensing.ensure_license_or_trial(
        root,
        "en",
        activation.StartupAuthorizationCheck("missing", "authorization.missing", None),
    )
    root.destroy()

    assert not accepted
    assert observed == {
        "activate_visible": True,
        "back_visible": True,
        "send_hidden": True,
        "send_restored": True,
        "email_focus_target": True,
    }
