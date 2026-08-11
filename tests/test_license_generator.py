from __future__ import annotations

from tools.license_generator import default_license_id, normalize_machine_code


def test_normalize_machine_code_accepts_pasted_variants() -> None:
    assert normalize_machine_code(" d498 c0d1-7c76 26cb ") == "D498-C0D1-7C76-26CB"


def test_normalize_machine_code_keeps_invalid_input_for_validation() -> None:
    assert normalize_machine_code("not-a-machine-code") == "NOT-A-MACHINE-CODE"


def test_default_license_id_is_nonempty_and_identifiable() -> None:
    assert default_license_id().startswith("LJR-")
