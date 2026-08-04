from src.camera_devices import CameraDevice, _parse_camera_names, enumerate_camera_devices, windows_camera_names


def test_camera_name_json_parser_handles_single_multiple_and_duplicates():
    assert _parse_camera_names('"Integrated Camera"') == ["Integrated Camera"]
    assert _parse_camera_names('["Integrated Camera","OBS Virtual Camera","Integrated Camera"]') == [
        "Integrated Camera", "OBS Virtual Camera",
    ]
    assert _parse_camera_names("not-json") == []


def test_camera_choices_keep_indices_and_configured_fallback(monkeypatch):
    windows_camera_names.cache_clear()
    monkeypatch.setattr("src.camera_devices.windows_camera_names", lambda: ("Lenovo Built-in", "OBS Virtual Camera"))
    devices = enumerate_camera_devices(1)
    assert devices == [CameraDevice(0, "Lenovo Built-in"), CameraDevice(1, "OBS Virtual Camera")]
    assert devices[1].label == "1 · OBS Virtual Camera"

    monkeypatch.setattr("src.camera_devices.windows_camera_names", lambda: ())
    assert enumerate_camera_devices(3) == [CameraDevice(3, "Camera 3 (configured)")]
