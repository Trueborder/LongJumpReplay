from dataclasses import asdict

from src.config import AppConfig, config_from_dict, load_config, save_config


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


def test_invalid_theme_rejected():
    try:
        config_from_dict({'display': {'theme': 'neon-chaos'}})
    except ValueError as exc:
        assert 'theme' in str(exc)
    else:
        raise AssertionError('invalid theme accepted')


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
