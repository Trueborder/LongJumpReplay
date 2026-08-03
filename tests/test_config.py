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


def test_invalid_theme_rejected():
    try:
        config_from_dict({'display': {'theme': 'neon-chaos'}})
    except ValueError as exc:
        assert 'theme' in str(exc)
    else:
        raise AssertionError('invalid theme accepted')
