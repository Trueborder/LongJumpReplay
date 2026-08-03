from src.i18n import CS, EN


def test_english_and_czech_translation_keys_stay_in_sync():
    assert EN.keys() == CS.keys()
