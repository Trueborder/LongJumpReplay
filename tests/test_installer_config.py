from pathlib import Path


def test_desktop_shortcut_is_unconditional():
    installer = Path(__file__).parents[1] / "packaging" / "LongJumpReplay.iss"
    text = installer.read_text(encoding="utf-8")

    assert "[Tasks]" not in text
    assert 'Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"' in text
    assert "Tasks: desktopicon" not in text


def test_portable_build_embeds_generated_defaults_not_developer_config():
    project = Path(__file__).parents[1]
    spec = (project / "packaging" / "LongJumpReplay.spec").read_text(encoding="utf-8")
    build = (project / "scripts" / "build" / "BUILD_PORTABLE.bat").read_text(encoding="utf-8")

    assert "packaging/generated/config.json" in spec
    assert "project_root, 'config.json'" not in spec
    assert "write_default_config.py" in build
