from pathlib import Path


def test_desktop_shortcut_is_unconditional():
    installer = Path(__file__).parents[1] / "packaging" / "LongJumpReplay.iss"
    text = installer.read_text(encoding="utf-8")

    assert "[Tasks]" not in text
    assert 'Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"' in text
    assert "Tasks: desktopicon" not in text
