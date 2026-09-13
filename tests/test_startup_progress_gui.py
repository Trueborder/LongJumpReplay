import time
import tkinter as tk

import pytest

from app import ACTIVATION_STARTUP_MINIMUM_SECONDS, StartupWindow
from src.progress import ProgressState, StartupProgressEvent


@pytest.mark.parametrize("language", ["en", "cs"])
def test_startup_progress_is_monotonic_and_details_are_remembered(language):
    root = tk.Tk(); root.withdraw()
    window = StartupWindow(root, language)
    remembered = []
    window.set_preference_callback(remembered.append)
    observed = []
    for event in (
        StartupProgressEvent("settings", "Settings", 1, 1, .1),
        StartupProgressEvent("components", "Components", 1, 2, .2),
        StartupProgressEvent("interface", "Interface", 7, 8, .4),
        StartupProgressEvent("services", "Services", 4, 4, .1),
    ):
        window.emit(event)
        observed.append(float(window.overall_bar.cget("value")))
    assert observed == sorted(observed)
    assert observed[-1] == 99
    window.emit(StartupProgressEvent("services", "Ready", 4, 4, .1, state=ProgressState.COMPLETED))
    assert float(window.overall_bar.cget("value")) == 100
    window.details_button.invoke(); root.update_idletasks()
    assert remembered == [True]
    assert window.details_frame.winfo_manager()
    root.destroy()


def test_startup_window_remains_responsive_during_minimum_activation_delay():
    root = tk.Tk(); root.withdraw()
    window = StartupWindow(root)
    callback_ran = []
    root.after(20, lambda: callback_ran.append(True))
    started = time.monotonic()

    window.wait_until_visible_for(0.1)

    assert time.monotonic() - started >= 0.08
    assert callback_ran == [True]
    assert ACTIVATION_STARTUP_MINIMUM_SECONDS == 2.0
    root.destroy()


def test_startup_window_destroy_removes_the_top_level():
    root = tk.Tk(); root.withdraw()
    window = StartupWindow(root)
    path = str(window.window)

    window.destroy()
    root.update_idletasks()

    assert int(root.tk.call("winfo", "exists", path)) == 0
    root.destroy()
