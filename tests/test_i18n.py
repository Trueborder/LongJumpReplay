from src.i18n import CS, EN, Translator
from src.language_catalog import (
    CORE_KEYS,
    LANGUAGE_NAMES,
    LANGUAGE_OPTIONS,
    SUPPORTED_LANGUAGES,
    TRANSLATION_OVERRIDES,
    language_from_option,
    language_option,
)
from src.main_window import camera_waiting_messages, first_available_camera


def test_english_and_czech_translation_keys_stay_in_sync():
    assert EN.keys() == CS.keys()


def test_world_language_catalog_includes_requested_central_european_languages():
    assert {"sk", "pl", "hu", "de"} <= set(SUPPORTED_LANGUAGES)
    assert {"zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "id", "ur"} <= set(SUPPORTED_LANGUAGES)
    assert tuple(LANGUAGE_NAMES) == SUPPORTED_LANGUAGES
    assert len(LANGUAGE_OPTIONS) == len(SUPPORTED_LANGUAGES)


def test_language_options_round_trip_to_config_codes():
    for code in SUPPORTED_LANGUAGES:
        assert language_from_option(language_option(code)) == code


def test_all_language_overrides_are_known_and_fall_back_to_english():
    assert set(TRANSLATION_OVERRIDES) == set(SUPPORTED_LANGUAGES) - {"en", "cs"}
    assert set(CORE_KEYS) <= set(EN)
    for code, table in TRANSLATION_OVERRIDES.items():
        assert table.keys() == set(CORE_KEYS), code
        translator = Translator(code)
        assert translator("button.freeze") == table["button.freeze"]
        assert translator("camera.help_title") == EN["camera.help_title"]


def test_unknown_language_falls_back_to_english():
    translator = Translator("xx")
    assert translator.language == "en"
    assert translator("button.freeze") == EN["button.freeze"]


def test_camera_waiting_message_keeps_initial_copy_and_supports_selected_index():
    initial = camera_waiting_messages(Translator("en"), "camera", 0, False)
    selected = camera_waiting_messages(Translator("en"), "camera", 1, True)
    assert initial == ("Looking for input from all sources", "Checking camera 0 and camera 1…")
    assert selected == ("Looking for input from camera 1", "Checking camera 1…")


def test_first_available_camera_prefers_camera_zero_and_waits_for_probe_results():
    assert first_available_camera({0: True, 1: True}) == 0
    assert first_available_camera({0: False, 1: True}) == 1
    assert first_available_camera({0: False, 1: None}) is None


def test_camera_waiting_message_uses_file_loading_copy_for_file_sources():
    file_source = camera_waiting_messages(Translator("en"), "file", 0, False)
    assert file_source == ("Loading file source", "Opening the selected video file…")


def test_board_target_formats_numeric_athlete_number():
    assert Translator("en")("board.target", athlete=7, attempt=1, limit=3) == "Athlete #07  ·  Attempt 1/3"
    assert Translator("cs")("board.target", athlete=7, attempt=1, limit=3) == "Závodník #07  ·  Pokus 1/3"
