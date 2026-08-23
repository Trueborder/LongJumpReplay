import tkinter as tk
from tkinter import ttk

import pytest

from src import activation, licensing, trial


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


@pytest.mark.parametrize("language", ["en", "cs"])
def test_code_step_has_back_and_activate_actions(monkeypatch, language):
    monkeypatch.setattr(activation, "request_code", lambda _email: 10)
    monkeypatch.setattr(
        trial,
        "refresh_trial_status",
        lambda: trial.TrialStatus(False, False, 0, 3, None),
    )

    root = tk.Tk()
    root.withdraw()
    observed = {}
    copy = licensing._trial_copy(language)

    def drive_dialog():
        dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        email = next(widget for widget in _descendants(dialog) if isinstance(widget, ttk.Entry))
        email.insert(0, "new@example.com")
        send = next(
            widget for widget in _descendants(dialog)
            if isinstance(widget, ttk.Button) and widget.cget("text") == copy["send"]
        )
        initial_height = dialog.winfo_height()
        send.invoke()
        dialog.update_idletasks()
        entries = [widget for widget in _descendants(dialog) if isinstance(widget, ttk.Entry)]
        code_entry = next(widget for widget in entries if widget is not email)
        code_entry.insert(0, "12a 34-56789")
        observed["code_formatted"] = code_entry.get()

        buttons = {
            widget.cget("text"): widget
            for widget in _descendants(dialog)
            if isinstance(widget, ttk.Button)
        }
        observed["activate_visible"] = buttons[copy["activate"]].winfo_ismapped()
        observed["back_visible"] = buttons[copy["back"]].winfo_ismapped()
        observed["send_hidden"] = not send.winfo_manager()
        observed["dialog_expanded"] = dialog.winfo_height() > initial_height
        dialog_bottom = dialog.winfo_rooty() + dialog.winfo_height()
        observed["actions_inside_dialog"] = all(
            button.winfo_rooty() + button.winfo_height() <= dialog_bottom
            for button in (buttons[copy["back"]], buttons[copy["activate"]])
        )

        buttons[copy["back"]].invoke()
        dialog.update_idletasks()
        observed["send_restored"] = bool(send.winfo_manager())
        observed["email_focus_target"] = dialog.focus_get() is email
        dialog.destroy()

    root.after(20, drive_dialog)
    accepted = licensing.ensure_license_or_trial(
        root,
        language,
        activation.StartupAuthorizationCheck("missing", "authorization.missing", None),
    )
    root.destroy()

    assert not accepted
    assert observed == {
        "activate_visible": True,
        "back_visible": True,
        "send_hidden": True,
        "dialog_expanded": True,
        "actions_inside_dialog": True,
        "code_formatted": "123456",
        "send_restored": True,
        "email_focus_target": True,
    }
