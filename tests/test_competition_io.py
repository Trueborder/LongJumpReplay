from __future__ import annotations

import csv
import json

import pytest

from src.adjudication import AdjudicationRecord, AthleteContext
from src.competition_io import (
    CsvExportAdapter,
    CsvImportAdapter,
    ExperimentalAk2ExportAdapter,
    JsonImportAdapter,
    XlsxImportAdapter,
)


def test_csv_import_is_staged_and_supports_czech_headers(tmp_path):
    source = tmp_path / "roster.csv"
    source.write_text("SČ;Jméno;Oddíl;Kategorie;Pořadí\n132;Jan Novak;AC Test;U18;2\n", encoding="utf-8-sig")
    draft = CsvImportAdapter().parse(source)
    assert draft.valid
    assert draft.athletes[0].bib == "132"
    assert draft.athletes[0].name == "Jan Novak"
    assert draft.athletes[0].club == "AC Test"
    assert draft.athletes[0].category == "U18"
    assert draft.athletes[0].start_order == 2


def test_invalid_import_returns_issues_without_athletes(tmp_path):
    source = tmp_path / "bad.json"
    source.write_text(json.dumps([{"bib": "1"}]), encoding="utf-8")
    draft = JsonImportAdapter().parse(source)
    assert not draft.valid
    assert draft.issues
    assert draft.athletes == []


def test_duplicate_import_rows_are_rejected(tmp_path):
    source = tmp_path / "duplicate.csv"
    source.write_text("name,bib,club\nA,1,C\nA,1,C\n", encoding="utf-8")
    draft = CsvImportAdapter().parse(source)
    assert not draft.valid
    assert any("Duplicate" in issue.message for issue in draft.issues)


def test_xlsx_import_chooses_sheet_with_named_roster(tmp_path):
    from openpyxl import Workbook

    source = tmp_path / "roster.xlsx"
    workbook = Workbook()
    workbook.active.append(["Notes"])
    roster = workbook.create_sheet("Start list")
    roster.append(["Bib", "Name", "Club", "Category", "Start order"])
    roster.append([145, "Eva Svoboda", "TJ Test", "Women", 1])
    workbook.save(source)

    draft = XlsxImportAdapter().parse(source)
    assert draft.valid
    assert draft.source_description.endswith("[Start list]")
    assert draft.athletes[0].name == "Eva Svoboda"


def test_generic_csv_export_contains_verdict_measurement_and_identity(tmp_path):
    destination = tmp_path / "decisions.csv"
    record = AdjudicationRecord(
        "record-1",
        1,
        AthleteContext("athlete-1", "Girls", 1, "145", "Eva Svoboda", "TJ Test", "Women", 1),
        2,
        "qualification",
        100.0,
        verdict="Valid",
        distance_cm=608,
        wind_tenths=-3,
    )
    report = CsvExportAdapter().export([record], destination)
    with destination.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert report.records_written == 1
    assert row["bib"] == "145"
    assert row["verdict"] == "Valid"
    assert row["distance_cm"] == "608"
    assert row["wind_mps"] == "-0.3"


def test_ak2_export_cannot_claim_unverified_compatibility(tmp_path):
    with pytest.raises(NotImplementedError, match="official sample"):
        ExperimentalAk2ExportAdapter().export([], tmp_path / "ak2.xml")
