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
        observed["action_groups"] = {
            widget.cget("text")
            for widget in _descendants(dialog)
            if isinstance(widget, ttk.LabelFrame)
        }

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
        "action_groups": {copy["licence_actions"], copy["evaluation_actions"]},
        "send_restored": True,
        "email_focus_target": True,
    }


def test_manual_activation_key_inserts_separators_without_moving_caret_back(monkeypatch):
    monkeypatch.setattr(
        trial,
        "refresh_trial_status",
        lambda: trial.TrialStatus(False, False, 0, 3, None),
    )

    root = tk.Tk()
    root.withdraw()
    observed = {}
    copy = licensing._trial_copy("en")

    def drive_dialog():
        dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        alternate = next(
            widget for widget in _descendants(dialog)
            if isinstance(widget, ttk.Button) and widget.cget("text") == copy["alternate"]
        )
        alternate.invoke()
        dialog.update()
        key_dialog = next(
            widget for widget in dialog.winfo_children()
            if isinstance(widget, tk.Toplevel)
        )
        key_entry = next(
            widget for widget in _descendants(key_dialog)
            if isinstance(widget, ttk.Entry)
        )

        for character in "1234":
            key_entry.insert(tk.INSERT, character)
            key_dialog.update()
        observed["first_group"] = key_entry.get()
        observed["first_cursor"] = key_entry.index(tk.INSERT)

        for character in "ABCD":
            key_entry.insert(tk.INSERT, character)
            key_dialog.update()
        observed["second_group"] = key_entry.get()
        observed["second_cursor"] = key_entry.index(tk.INSERT)

        key_dialog.destroy()
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
        "first_group": "1234-",
        "first_cursor": 5,
        "second_group": "1234-ABCD-",
        "second_cursor": 10,
    }
