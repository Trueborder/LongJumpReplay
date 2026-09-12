from pathlib import Path

from src.portable_paths import app_data_paths


def test_app_data_paths_keep_configured_roots_and_group_mutable_media(tmp_path):
    config_path = tmp_path / "config.json"
    paths = app_data_paths(config_path)

    assert paths.root == tmp_path
    assert paths.cache == tmp_path / "cache"
    assert paths.recordings == tmp_path / "recordings"
    assert paths.exports == tmp_path / "exports"
    assert paths.evidence == tmp_path / "exports" / "evidence"
    assert paths.adjudication == tmp_path / "adjudication"
    assert paths.thumbnails == tmp_path / "recordings" / ".thumbnails"


def test_app_data_paths_preserve_absolute_legacy_locations(tmp_path):
    legacy_cache = (tmp_path / "legacy-cache").resolve()
    legacy_recordings = (tmp_path / "legacy-recordings").resolve()
    paths = app_data_paths(
        tmp_path / "config.json",
        cache_directory=str(legacy_cache),
        recordings_directory=str(legacy_recordings),
    )

    assert paths.cache == legacy_cache
    assert paths.recordings == legacy_recordings
