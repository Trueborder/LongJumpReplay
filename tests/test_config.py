from dataclasses import asdict

from src.config import AppConfig, apply_low_resource_mode, config_from_dict, load_config, save_config


def test_config_round_trip(tmp_path):
    path = tmp_path / 'config.json'
    config = AppConfig()
    config.display.theme = 'light'
    config.hotkeys.bindings['freeze_toggle'] = 'F2'
    save_config(config, path)
    loaded = load_config(path)
    assert asdict(loaded) == asdict(config)


def test_old_partial_config_gets_new_defaults():
    config = config_from_dict({'camera': {'fps': 60}, 'display': {'theme': 'dark'}})
    assert config.camera.fps == 60
    assert config.attempts.retention_minutes == 10
    assert config.hotkeys.bindings['next_attempt'] == 'Control-Next'
    assert config.hotkeys.bindings['timer_toggle'] == ''
    assert config.athlete_timer.duration_seconds == 60
    assert config.display.window_maximized is False
    assert config.top_view_projection.legal_side_flipped is False
    assert config.top_view_projection.camera_profile == {}
    assert config.top_view_projection.foul_area == []


def test_legacy_timeline_zoom_is_migrated_to_one_second_to_one_hour():
    below = config_from_dict({"timeline": {
        "detail_window_seconds": 2.0,
        "min_detail_seconds": .1,
        "max_detail_seconds": 60.0,
    }})
    assert below.timeline.detail_window_seconds == 2.0
    assert below.timeline.min_detail_seconds == 1.0
    assert below.timeline.max_detail_seconds == 3600.0
    above = config_from_dict({"timeline": {"detail_window_seconds": 7200.0}})
    assert above.timeline.detail_window_seconds == 3600.0


def test_top_view_legal_side_and_optional_camera_profile_round_trip():
    profile = {"image_width": 1920, "rms_error_px": .24}
    config = config_from_dict({"top_view_projection": {
        "legal_side_flipped": True,
        "camera_profile": profile,
    }})
    assert config.top_view_projection.legal_side_flipped is True
    assert config.top_view_projection.camera_profile == profile


def test_four_corner_foul_area_round_trip():
    area = [[.45, .2], [.55, .2], [.55, .8], [.45, .8]]
    config = config_from_dict({"top_view_projection": {"foul_area": area}})
    assert config.top_view_projection.foul_area == area


def test_invalid_theme_rejected():
    try:
        config_from_dict({'display': {'theme': 'neon-chaos'}})
    except ValueError as exc:
        assert 'theme' in str(exc)
    else:
        raise AssertionError('invalid theme accepted')


def test_supported_world_languages_are_validated():
    for language in ("sk", "pl", "hu", "de", "zh", "hi", "es", "ar"):
        assert config_from_dict({"general": {"language": language}}).general.language == language
    try:
        config_from_dict({"general": {"language": "xx"}})
    except ValueError as exc:
        assert "general.language" in str(exc)
    else:
        raise AssertionError("unsupported language accepted")


def test_corrupt_config_is_quarantined_and_replaced_with_defaults(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"camera": [', encoding='utf-8')

    loaded = load_config(path)

    assert loaded == AppConfig()
    assert path.exists()
    assert path.with_name('config.json.corrupt').read_text(encoding='utf-8') == '{"camera": ['
    assert load_config(path) == AppConfig()


def test_invalid_nested_config_is_recovered(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text('{"display": {"theme": "not-a-theme"}}', encoding='utf-8')

    loaded = load_config(path)

    assert loaded.display.theme == AppConfig().display.theme
    assert path.with_name('config.json.corrupt').exists()


def test_athlete_timer_config_round_trip_and_validation(tmp_path):
    path = tmp_path / 'timer-config.json'
    config = AppConfig()
    config.athlete_timer.duration_seconds = 75
    save_config(config, path)
    assert load_config(path).athlete_timer.duration_seconds == 75
    for invalid in (0, 601, 1.5, True):
        try:
            config_from_dict({'athlete_timer': {'duration_seconds': invalid}})
        except ValueError as exc:
            assert 'athlete_timer.duration_seconds' in str(exc)
        else:
            raise AssertionError(f'invalid timer duration accepted: {invalid!r}')


def test_dangerous_runtime_values_and_duplicate_hotkeys_are_rejected():
    invalid_configs = [
        {'buffer': {'store_every_nth_frame': 0}},
        {'display': {'guide_width_px': 0}},
        {'takeoff_assist': {'quick_review_speed': 0}},
        {'hotkeys': {'bindings': {'freeze_toggle': 'F2', 'timer_toggle': 'f2'}}},
        {'camera': {'source_type': 'file', 'file_path': ''}},
    ]
    for data in invalid_configs:
        try:
            config_from_dict(data)
        except ValueError:
            pass
        else:
            raise AssertionError(f'invalid configuration accepted: {data!r}')


def test_low_resource_mode_reduces_work_without_lowering_camera_fps():
    config = AppConfig()
    config.camera.fps = 120
    apply_low_resource_mode(config)
    assert config.performance.preset == 'quiet'
    assert config.performance.preview_refresh_hz == 20
    assert config.performance.adaptive_enabled is True
    assert config.camera.fps == 120
    assert config.buffer.duration_seconds == 15
    assert config.buffer.jpeg_quality == 72
    assert config.buffer.encoder_queue_size == 64
    assert config.buffer.max_memory_mb == 1024
    assert config.buffer.store_every_nth_frame == 2
    config.validate()
