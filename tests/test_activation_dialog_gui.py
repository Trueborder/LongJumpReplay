import threading
import time
import tkinter as tk
from tkinter import ttk

import pytest

from src import activation, licensing, trial
from src.theme import ThemeManager


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _wait_until(root, predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.mark.parametrize("language", ["en", "cs"])
def test_code_step_has_back_and_activate_actions(monkeypatch, language):
    observed = {}
    request_started = threading.Event()
    release_request = threading.Event()

    def request_code(_email):
        request_started.set()
        release_request.wait(timeout=2)
        return 10

    monkeypatch.setattr(activation, "request_code", request_code)
    monkeypatch.setattr(
        trial,
        "refresh_trial_status",
        lambda: trial.TrialStatus(False, False, 0, 3, None),
    )

    root = tk.Tk()
    root.withdraw()
    ThemeManager(root).apply("dark")
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
        assert _wait_until(root, request_started.is_set)
        progress = next(
            widget for widget in _descendants(dialog)
            if isinstance(widget, ttk.Progressbar) and widget.winfo_ismapped()
        )
        initial_progress = float(progress.cget("value"))
        observed["progress_visible_while_working"] = progress.winfo_ismapped()
        observed["progress_mode"] = str(progress.cget("mode"))
        observed["progress_style"] = progress.cget("style")
        observed["progress_thickness"] = int(ttk.Style(root).lookup(progress.cget("style"), "thickness"))
        observed["progress_moves_while_working"] = _wait_until(
            root,
            lambda: float(progress.cget("value")) != initial_progress,
        )
        observed["send_disabled_while_working"] = send.instate(["disabled"])
        release_request.set()
        assert _wait_until(
            root,
            lambda: any(
                widget is not email and widget.winfo_ismapped()
                for widget in _descendants(dialog)
                if isinstance(widget, ttk.Entry)
            ),
        )
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
        "progress_visible_while_working": True,
        "progress_mode": "indeterminate",
        "progress_style": "Modal.Horizontal.TProgressbar",
        "progress_thickness": 10,
        "progress_moves_while_working": True,
        "send_disabled_while_working": True,
    }


def test_manual_activation_key_inserts_separators_without_moving_caret_back(monkeypatch):
    monkeypatch.setattr(
        trial,
        "refresh_trial_status",
        lambda: trial.TrialStatus(False, False, 0, 3, None),
    )

    root = tk.Tk()
    root.withdraw()
    ThemeManager(root).apply("dark")
    observed = {}
    copy = licensing._trial_copy("en")
    request_started = threading.Event()
    release_request = threading.Event()

    def activate_with_key(_key):
        request_started.set()
        release_request.wait(timeout=2)

    monkeypatch.setattr(activation, "activate_with_key", activate_with_key)

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

        for character in "EFGH":
            key_entry.insert(tk.INSERT, character)
            key_dialog.update()
        activate_button = next(
            widget for widget in _descendants(key_dialog)
            if isinstance(widget, ttk.Button) and widget.cget("text") == copy["key_activate"]
        )
        activate_button.invoke()
        assert _wait_until(root, request_started.is_set)
        progress = next(
            widget for widget in _descendants(key_dialog)
            if isinstance(widget, ttk.Progressbar) and widget.winfo_ismapped()
        )
        initial_progress = float(progress.cget("value"))
        observed["progress_visible_while_working"] = progress.winfo_ismapped()
        observed["progress_mode"] = str(progress.cget("mode"))
        observed["progress_style"] = progress.cget("style")
        observed["progress_thickness"] = int(ttk.Style(root).lookup(progress.cget("style"), "thickness"))
        observed["progress_moves_while_working"] = _wait_until(
            root,
            lambda: float(progress.cget("value")) != initial_progress,
        )
        observed["activate_disabled_while_working"] = activate_button.instate(["disabled"])
        release_request.set()

    root.after(20, drive_dialog)
    accepted = licensing.ensure_license_or_trial(
        root,
        "en",
        activation.StartupAuthorizationCheck("missing", "authorization.missing", None),
    )
    root.destroy()

    assert accepted
    assert observed == {
        "first_group": "1234-",
        "first_cursor": 5,
        "second_group": "1234-ABCD-",
        "second_cursor": 10,
        "progress_visible_while_working": True,
        "progress_mode": "indeterminate",
        "progress_style": "Modal.Horizontal.TProgressbar",
        "progress_thickness": 10,
        "progress_moves_while_working": True,
        "activate_disabled_while_working": True,
    }
