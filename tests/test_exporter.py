from src.exporter import export_clip, normalise_video_fps
from src.models import FramePacket


def test_encoder_fps_normalisation_snaps_capture_clock_noise():
    assert normalise_video_fps(119.999) == 120.0
    assert normalise_video_fps(59.941) == 59.94
    assert normalise_video_fps(117.346) == 117.35


def test_near_120fps_export_stays_mp4(tmp_path, jpeg_frame):
    jpeg, frame = jpeg_frame
    height, width = frame.shape[:2]
    interval_ns = 8_333_403  # approximately 119.999 fps
    packets = [
        FramePacket(index, index * interval_ns, jpeg, width, height)
        for index in range(24)
    ]
    result = export_clip(
        packets,
        tmp_path,
        preferred_codec="mp4v",
        write_sidecar_json=False,
        base_name="near_120fps",
    )
    assert result.video_path.suffix.lower() == ".mp4"
    assert result.video_path.exists()
    assert result.fps == 120.0
