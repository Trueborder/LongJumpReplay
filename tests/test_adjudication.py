from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.adjudication import (
    AdjudicationSessionStore,
    AthleteContext,
    BoardReferenceState,
    parse_distance_centimetres,
    parse_wind_metres_per_second,
)
from src.models import AttemptSession, AttemptState


def _attempt(attempt_id: int = 7) -> AttemptSession:
    return AttemptSession(
        attempt_id=attempt_id,
        created_monotonic_ns=10,
        created_wall_time=1_700_000_000.0,
        freeze_timestamp_ns=20,
        pre_seconds=1.0,
        post_seconds=1.0,
        expires_at_wall_time=1_700_000_600.0,
        state=AttemptState.READY,
        competitor_group="Boys",
        competitor_number=3,
        competitor_attempt_number=2,
        temp_video_path=Path("attempt.mp4"),
    )


def test_measurement_parsing_uses_whole_centimetres():
    assert parse_distance_centimetres("621") == 621
    assert parse_wind_metres_per_second("+1,7") == 17
    assert parse_wind_metres_per_second("") is None
    with pytest.raises(ValueError):
        parse_distance_centimetres("6.21")
    with pytest.raises(ValueError):
        parse_wind_metres_per_second("1.75")


def test_verdict_and_measurement_survive_without_temporary_media(tmp_path):
    store = AdjudicationSessionStore(tmp_path / "session")
    attempt = _attempt()
    record = store.ensure_attempt(
        attempt,
        athlete=AthleteContext("athlete-3", "Boys", 3, "132", "Novak", "AC", "U18", 3),
        camera_source="Camera 0",
        board_reference=BoardReferenceState(True, .4, .5, 2.0, 2, [.1, .2, .3, .4]),
    )
    decided = store.record_verdict(record.record_id, "Valid", frame_index=15, frame_timestamp_ns=123, now=1_700_000_004.0)
    store.set_measurement(decided.record_id, distance_cm=621, wind_tenths=17)
    store.mark_media_unavailable(decided.record_id)
    store.close()

    recovered = AdjudicationSessionStore(tmp_path / "session")
    restored = recovered.get(record.record_id)
    assert restored is not None
    assert restored.verdict == "Valid"
    assert restored.distance_cm == 621
    assert restored.wind_tenths == 17
    assert restored.media_available is False
    assert restored.selected_frame_index == 15
    assert restored.athlete.name == "Novak"


def test_journal_recovers_update_when_snapshot_is_corrupt(tmp_path):
    directory = tmp_path / "session"
    store = AdjudicationSessionStore(directory)
    record = store.ensure_attempt(_attempt())
    store.record_verdict(record.record_id, "Foul", frame_index=4, frame_timestamp_ns=99)
    directory.joinpath("adjudication-session.json").write_text("{broken", encoding="utf-8")

    recovered = AdjudicationSessionStore(directory)
    restored = recovered.get(record.record_id)
    assert restored and restored.verdict == "Foul"
    assert recovered.recovery_warnings


def test_restart_reattaches_record_if_attempt_id_metadata_write_was_interrupted(tmp_path):
    directory = tmp_path / "session"
    attempt = _attempt()
    first = AdjudicationSessionStore(directory)
    created = first.ensure_attempt(attempt)

    recovered = AdjudicationSessionStore(directory)
    reattached = recovered.ensure_attempt(attempt)
    assert reattached.record_id == created.record_id
    assert len(recovered.records()) == 1


def test_evidence_hashes_are_persisted(tmp_path):
    store = AdjudicationSessionStore(tmp_path / "session")
    record = store.ensure_attempt(_attempt())
    raw = tmp_path / "raw.png"
    metadata = tmp_path / "raw.json"
    raw.write_bytes(b"clean camera pixels")
    metadata.write_text(json.dumps({"layers": "separate"}), encoding="utf-8")
    updated = store.set_evidence(record.record_id, raw_path=raw, annotated_path=None, metadata_path=metadata)
    assert updated.evidence.hashes["raw"]
    assert updated.evidence.hashes["metadata"]


def test_roster_replace_is_atomic_from_the_public_api(tmp_path):
    store = AdjudicationSessionStore(tmp_path / "session")
    athletes = [AthleteContext("a1", "Boys", 1, "132", "Novak", "AC", "U18", 1)]
    store.replace_roster(athletes)
    assert store.athlete_for("Boys", 1).bib == "132"


def test_hundreds_of_attempts_survive_compaction_and_restart(tmp_path):
    directory = tmp_path / "long-session"
    store = AdjudicationSessionStore(directory)
    for attempt_id in range(1, 301):
        attempt = _attempt(attempt_id)
        attempt.competitor_number = ((attempt_id - 1) % 50) + 1
        attempt.competitor_attempt_number = ((attempt_id - 1) // 50) + 1
        record = store.ensure_attempt(attempt)
        verdict = ("Valid", "Foul", "Review")[attempt_id % 3]
        store.record_verdict(
            record.record_id,
            verdict,
            frame_index=attempt_id % 120,
            frame_timestamp_ns=attempt_id * 1_000_000,
            now=attempt.created_wall_time + 3.0,
        )
    store.close()

    recovered = AdjudicationSessionStore(directory)
    report = recovered.session_report()
    assert len(recovered.records()) == 300
    assert report["attempts_processed"] == 300
    assert report["lost_attempts"] == 0
    assert report["median_decision_seconds"] == 3.0
