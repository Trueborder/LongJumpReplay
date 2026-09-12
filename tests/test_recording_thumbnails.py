import time
from pathlib import Path
from queue import Queue

import cv2
import numpy as np

from src.recording_thumbnails import RecordingThumbnailWorker


def test_thumbnail_generation_is_async_and_cached(monkeypatch, tmp_path):
    source = tmp_path / "recording.mp4"
    source.write_bytes(b"source")

    class FakeCapture:
        def isOpened(self):
            return True

        def set(self, _property, _value):
            return True

        def read(self):
            return True, np.zeros((12, 16, 3), dtype=np.uint8)

        def release(self):
            return None

    def fake_imwrite(path, _frame):
        Path(path).write_bytes(b"thumbnail")
        return True

    monkeypatch.setattr(cv2, "VideoCapture", lambda _path: FakeCapture())
    monkeypatch.setattr(cv2, "imwrite", fake_imwrite)
    events = Queue()
    worker = RecordingThumbnailWorker(tmp_path / "thumbs", events)
    worker.start()
    worker.request(4, source)
    worker.request(4, source, 9)
    deadline = time.time() + 2
    while time.time() < deadline and events.qsize() < 2:
        time.sleep(.01)
    worker.stop()

    ready = [events.get_nowait() for _ in range(2)]
    assert all(event == "recording_thumbnail_ready" for event, _payload in ready)
    paths = [payload[1] for _event, payload in ready]
    assert len(set(paths)) == 2
    assert any("_f000000.png" in path.name for path in paths)
    assert any("_f000009.png" in path.name for path in paths)
    assert all(path.exists() and path.read_bytes() == b"thumbnail" for path in paths)
