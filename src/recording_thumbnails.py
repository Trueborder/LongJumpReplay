from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread

import cv2


class RecordingThumbnailWorker:
    """Generate cached recording thumbnails without touching the Tk thread."""

    def __init__(self, thumbnail_directory: Path, event_queue: Queue[tuple[str, object]], size: tuple[int, int] = (72, 44)) -> None:
        self.thumbnail_directory = Path(thumbnail_directory)
        self.event_queue = event_queue
        self.size = size
        self._queue: Queue[tuple[int, Path, int, str]] = Queue()
        self._pending: set[tuple[int, str, int]] = set()
        self._published: set[Path] = set()
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        self.thumbnail_directory.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="recording-thumbnails", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(max(0.0, timeout))

    def request(self, attempt_id: int, video_path: Path | None, frame_index: int = 0) -> None:
        if not video_path or not video_path.exists():
            return
        try:
            stamp = f"{video_path.stat().st_size}-{video_path.stat().st_mtime_ns}"
        except OSError:
            return
        key = (int(attempt_id), stamp, max(0, int(frame_index)))
        target = self.thumbnail_directory / f"recording_{attempt_id:04d}_{stamp}_f{key[2]:06d}.png"
        if target.exists():
            with self._lock:
                already_published = target in self._published
                self._published.add(target)
            if not already_published:
                self.event_queue.put(("recording_thumbnail_ready", (attempt_id, target)))
            return
        with self._lock:
            if key in self._pending:
                return
            self._pending.add(key)
        self._queue.put((int(attempt_id), Path(video_path), max(0, int(frame_index)), stamp))

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                attempt_id, video_path, frame_index, stamp = self._queue.get(timeout=.1)
            except Empty:
                continue
            target = self.thumbnail_directory / f"recording_{attempt_id:04d}_{stamp}_f{frame_index:06d}.png"
            try:
                capture = cv2.VideoCapture(str(video_path))
                try:
                    if not capture.isOpened():
                        raise RuntimeError("video could not be opened")
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ok, frame = capture.read()
                    if not ok or frame is None:
                        raise RuntimeError("no video frame available")
                    width, height = self.size
                    thumb = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                    temporary = target.with_name(target.name + ".tmp.png")
                    if not cv2.imwrite(str(temporary), thumb):
                        raise RuntimeError("thumbnail could not be written")
                    temporary.replace(target)
                    with self._lock:
                        self._published.add(target)
                finally:
                    capture.release()
                self.event_queue.put(("recording_thumbnail_ready", (attempt_id, target)))
            except Exception as exc:
                self.event_queue.put(("recording_thumbnail_failed", (attempt_id, str(exc))))
            finally:
                with self._lock:
                    self._pending.discard((attempt_id, stamp, frame_index))
                self._queue.task_done()
