from dataclasses import dataclass
from pathlib import Path
import json

import pytest

from src.adjudication import AdjudicationSessionStore, AthleteContext
from src.session_storage import RetentionPlan, SessionStore


@dataclass
class _Competition:
    name: str
    export_root: Path


def test_session_manifest_is_atomic_and_json_safe(tmp_path):
    store = SessionStore(tmp_path / "sessions", "Meet / 2026")
    manifest = store.write_manifest(
        competition=_Competition("Local meet", tmp_path / "exports"),
        attempts=[{"attempt_id": 4, "temp_video_path": tmp_path / "attempt.mp4"}],
        roster=[AthleteContext("a1", "Boys", 1, "7", "Ada Athlete", "Club", "U18", 1)],
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["state"] == "open"
    assert payload["competition"]["export_root"] == str(tmp_path / "exports")
    assert payload["roster"][0]["name"] == "Ada Athlete"
    assert not manifest.with_suffix(".json.tmp").exists()


def test_session_retention_moves_unselected_categories_to_recoverable_trash(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    store.manifest_path.write_text("manifest", encoding="utf-8")
    store.paths.recordings.joinpath("recording.mp4").write_bytes(b"video")
    store.paths.diagnostics.joinpath("app.log").write_text("log", encoding="utf-8")

    moved = store.apply_retention(RetentionPlan(recordings=False, diagnostics=False))

    assert store.manifest_path.exists()
    assert not store.paths.recordings.exists()
    assert not store.paths.diagnostics.exists()
    assert len(moved) == 2
    trash = tmp_path / "sessions" / ".LongJumpReplay-Trash"
    assert len(list(trash.iterdir())) == 2


def test_group_roster_can_be_reordered_and_extended_before_attempts(tmp_path):
    store = AdjudicationSessionStore(tmp_path / "adjudication")
    store.replace_group_roster(
        "Boys",
        [
            AthleteContext("a2", "Boys", 1, "2", "Second", "Club B", "U18", 1),
            AthleteContext("a1", "Boys", 2, "1", "First", "Club A", "U18", 2),
        ],
    )
    store.replace_group_roster(
        "Boys",
        [
            AthleteContext("a1", "Boys", 1, "1", "First", "Club A", "U18", 1),
            AthleteContext("a2", "Boys", 2, "2", "Second", "Club B", "U18", 2),
            AthleteContext("a3", "Boys", 3, "3", "Third", "Club C", "U18", 3),
        ],
    )

    roster = store.roster()
    assert [item.name for item in roster] == ["First", "Second", "Third"]
    assert [item.competitor_number for item in roster] == [1, 2, 3]


def test_group_roster_is_locked_after_a_record_exists(tmp_path):
    store = AdjudicationSessionStore(tmp_path / "adjudication")
    from src.models import AttemptSession, AttemptState

    attempt = AttemptSession(
        attempt_id=1,
        created_monotonic_ns=1,
        created_wall_time=1.0,
        freeze_timestamp_ns=1,
        pre_seconds=1.0,
        post_seconds=1.0,
        expires_at_wall_time=2.0,
        state=AttemptState.READY,
        competitor_group="Boys",
        competitor_number=1,
        competitor_attempt_number=1,
    )
    store.ensure_attempt(attempt, athlete=AthleteContext("a1", "Boys", 1, "1", "First", "", "U18", 1))
    with pytest.raises(ValueError):
        store.replace_group_roster("Boys", [AthleteContext("a1", "Boys", 1, "1", "First", "", "U18", 1)])


def test_retention_can_move_current_recording_outside_session_folder(tmp_path):
    store = SessionStore(tmp_path / "sessions")
    recording = tmp_path / "legacy-recording.mp4"
    recording.write_bytes(b"video")

    moved = store.apply_retention(RetentionPlan(recordings=False), external_recordings=[recording])

    assert not recording.exists()
    assert recording in moved