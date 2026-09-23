from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

import cv2
import numpy as np
import pytest


def _install_tk_startup_retry() -> None:
    import tkinter

    if getattr(tkinter, "_ljr_tk_startup_retry", False):
        return
    original_tk = tkinter.Tk

    def create_tk(*args, **kwargs):
        last_error = None
        for attempt in range(5):
            try:
                return original_tk(*args, **kwargs)
            except tkinter.TclError as exc:
                last_error = exc
                message = str(exc)
                if not any(token in message for token in (
                    "tcl_findLibrary", "init.tcl", "usable init.tcl",
                    "Can't find a usable tk.tcl", "couldn't read file",
                )):
                    raise
                _configure_tk_library_paths()
                if attempt < 4:
                    time.sleep(0.1)
        assert last_error is not None
        raise last_error

    tkinter.Tk = create_tk
    tkinter._ljr_tk_startup_retry = True


def _configure_tk_library_paths() -> None:
    tcl_root = Path(sys.base_prefix) / "tcl"
    tcl_dir = next((path for path in tcl_root.glob("tcl*") if (path / "init.tcl").is_file()), None)
    tk_dir = next((path for path in tcl_root.glob("tk*") if (path / "tk.tcl").is_file()), None)
    if tcl_dir is not None and not Path(os.environ.get("TCL_LIBRARY", ""), "init.tcl").is_file():
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir is not None and not Path(os.environ.get("TK_LIBRARY", ""), "tk.tcl").is_file():
        os.environ["TK_LIBRARY"] = str(tk_dir)


def pytest_configure(config: pytest.Config) -> None:
    """Avoid reusing pytest temp roots created by another Windows account."""
    _configure_tk_library_paths()
    _install_tk_startup_retry()
    if config.option.basetemp is None:
        config.option.basetemp = str(
            Path(tempfile.gettempdir())
            / f"LongJumpReplay-pytest-{uuid.uuid4().hex}"
        )


@pytest.fixture
def jpeg_frame():
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    cv2.rectangle(frame, (30, 20), (120, 70), (0, 180, 255), -1)
    ok, data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    assert ok
    return data.tobytes(), frame


@pytest.fixture(autouse=True)
def noninteractive_main_window_shutdown(monkeypatch):
    """Keep existing GUI tests non-blocking while production close stays interactive."""
    from src.main_window import MainWindow
    from src.session_storage import RetentionPlan

    monkeypatch.setattr(MainWindow, "_show_shutdown_dialog", lambda _self: RetentionPlan())