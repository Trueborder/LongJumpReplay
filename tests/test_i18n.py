from src.i18n import CS, EN, Translator
from src.main_window import camera_waiting_messages, first_available_camera


def test_english_and_czech_translation_keys_stay_in_sync():
    assert EN.keys() == CS.keys()


def test_camera_waiting_message_keeps_initial_copy_and_supports_selected_index():
    initial = camera_waiting_messages(Translator("en"), "camera", 0, False)
    selected = camera_waiting_messages(Translator("en"), "camera", 1, True)
    assert initial == ("Looking for input from all sources", "Checking camera 0 and camera 1…")
    assert selected == ("Looking for input from camera 1", "Checking camera 1…")


def test_first_available_camera_prefers_camera_zero_and_waits_for_probe_results():
    assert first_available_camera({0: True, 1: True}) == 0
    assert first_available_camera({0: False, 1: True}) == 1
    assert first_available_camera({0: False, 1: None}) is None
