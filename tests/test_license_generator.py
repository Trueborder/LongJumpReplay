from __future__ import annotations

import tkinter as tk

from tools.license_generator import (
    default_license_id,
    destroy_root,
    format_machine_code_input,
    normalize_machine_code,
)


def test_normalize_machine_code_accepts_pasted_variants() -> None:
    assert normalize_machine_code(" d498 c0d1-7c76 26cb ") == "D498-C0D1-7C76-26CB"


def test_normalize_machine_code_keeps_invalid_input_for_validation() -> None:
    assert normalize_machine_code("not-a-machine-code") == "NOT-A-MACHINE-CODE"


def test_format_machine_code_input_formats_filters_and_limits() -> None:
    assert format_machine_code_input("d498c0d17c7626cb") == "D498-C0D1-7C76-26CB"
    assert format_machine_code_input("d498 c0d1-$7c76_26cb-more") == "D498-C0D1-7C76-26CB"
    assert format_machine_code_input("1234567890abcdef9999") == "1234-5678-90AB-CDEF"


def test_destroy_root_ignores_an_already_destroyed_tk_application() -> None:
    class DestroyedRoot:
        def destroy(self) -> None:
            raise tk.TclError('can\'t invoke "destroy" command: application has been destroyed')

    destroy_root(DestroyedRoot())  # type: ignore[arg-type]


def test_default_license_id_is_nonempty_and_identifiable() -> None:
    assert default_license_id().startswith("LJR-")
