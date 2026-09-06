from __future__ import annotations

from collections import deque
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
import logging
import time
from typing import Callable, Protocol

import cv2
import numpy as np

from .config import BufferConfig, CameraConfig
from .models import CaptureStats, FramePacket
from .ring_buffer import TimeRingBuffer


class VideoSource(Protocol):
    description: str
    def open(self) -> None: ...
    def read(self) -> tuple[bool, np.ndarray | None]: ...
    def close(self) -> None: ...


class LatestFrameStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._frame: np.ndarray | None = None
        self._timestamp_ns = 0
        self._capture_index = -1

    def update(self, frame: np.ndarray, timestamp_ns: int, capture_index: int) -> None:
        with self._lock:
            self._frame = frame
            self._timestamp_ns = timestamp_ns
            self._capture_index = capture_index

    def get(self) -> tuple[np.ndarray | None, int, int]:
        with self._lock:
            return self._frame, self._timestamp_ns, self._capture_index

    def clear(self) -> None:
        with self._lock:
            self._frame = None
            self._timestamp_ns = 0
            self._capture_index = -1


class SyntheticSource:
    description = "Synthetic 120 fps camera"

    def __init__(self, width: int, height: int, fps: float) -> None:
        self.width, self.height, self.fps = width, height, fps
        self._frame_index = 0
        self._next_deadline = 0.0
        self._closed = Event()
        self._base = self._make_background()

    def _make_background(self) -> np.ndarray:
        frame = np.full((self.height, self.width, 3), 28, dtype=np.uint8)
        for x in range(0, self.width, max(40, self.width // 16)):
            cv2.line(frame, (x, 0), (x, self.height), (45, 45, 45), 1)
        for y in range(0, self.height, max(40, self.height // 10)):
            cv2.line(frame, (0, y), (self.width, y), (45, 45, 45), 1)
        board_x = int(self.width * 0.62)
        cv2.rectangle(frame, (board_x - 5, int(self.height * .15)), (board_x + 5, int(self.height * .85)), (235, 235, 235), -1)
        cv2.line(frame, (board_x, 0), (board_x, self.height), (0, 85, 255), 2)
        cv2.putText(frame, "SYNTHETIC CAMERA", (24, 42), cv2.FONT_HERSHEY_SIMPLEX, .9, (230, 230, 230), 2, cv2.LINE_AA)
        return frame

    def open(self) -> None:
        self._closed.clear()
        self._frame_index = 0
        self._next_deadline = time.perf_counter()

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._closed.is_set():
            return False, None
        period = 1.0 / self.fps
        now = time.perf_counter()
        if now < self._next_deadline:
            self._closed.wait(self._next_deadline - now)
        elif now - self._next_deadline > .25:
            self._next_deadline = now
        if self._closed.is_set():
            return False, None
        self._next_deadline += period
        frame = self._base.copy()
        phase = (self._frame_index % max(1, int(self.fps * 2))) / max(1.0, self.fps * 2)
        x = int((.08 + .84 * phase) * self.width)
        y = int(self.height * (.55 + .08 * np.sin(phase * np.pi * 4)))
        shoe_w, shoe_h = max(24, self.width // 18), max(10, self.height // 35)
        cv2.rectangle(frame, (x - shoe_w // 2, y - shoe_h // 2), (x + shoe_w // 2, y + shoe_h // 2), (70, 210, 255), -1)
        cv2.putText(frame, f"Frame {self._frame_index:08d} | {self.fps:.1f} fps", (24, self.height - 26), cv2.FONT_HERSHEY_SIMPLEX, .75, (230, 230, 230), 2, cv2.LINE_AA)
        self._frame_index += 1
        return True, frame

    def close(self) -> None:
        self._closed.set()


class OpenCVCameraSource:
    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self.cap: cv2.VideoCapture | None = None
        self.description = f"Camera {config.device_index}"
        self._lock = Lock()

    @staticmethod
    def _backend(name: str) -> int:
        return {"DSHOW": cv2.CAP_DSHOW, "MSMF": cv2.CAP_MSMF, "ANY": cv2.CAP_ANY}.get(name.upper(), cv2.CAP_ANY)

    def open(self) -> None:
        cap = cv2.VideoCapture(self.config.device_index, self._backend(self.config.backend))
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Could not open camera {self.config.device_index} using {self.config.backend}.")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.config.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        cap.set(cv2.CAP_PROP_FPS, self.config.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)
        with self._lock:
            self.cap = cap
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        backend = cap.getBackendName() if hasattr(cap, "getBackendName") else self.config.backend
        self.description = f"Camera {self.config.device_index} · {width}×{height} · reported {fps:.1f} fps · {backend}"

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            cap = self.cap
        if cap is None:
            return False, None
        return cap.read()

    def close(self) -> None:
        with self._lock:
            cap, self.cap = self.cap, None
        if cap is not None:
            cap.release()


class VideoFileSource:
    def __init__(self, path: str, loop: bool) -> None:
        self.path, self.loop = Path(path), loop
        self.cap: cv2.VideoCapture | None = None
        self.description = f"File {self.path.name}"
        self._fps = 30.0
        self._next_deadline = 0.0
        self._closed = Event()

    def open(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"Video file does not exist: {self.path}")
        self.cap = cv2.VideoCapture(str(self.path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video: {self.path}")
        fps = float(self.cap.get(cv2.CAP_PROP_FPS))
        self._fps = fps if fps > 0 else 30.0
        self._next_deadline = time.perf_counter()
        self._closed.clear()
        width, height = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.description = f"File {self.path.name} · {width}×{height} · {self._fps:.1f} fps"

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.cap is None or self._closed.is_set():
            return False, None
        now = time.perf_counter()
        if now < self._next_deadline:
            self._closed.wait(self._next_deadline - now)
        elif now - self._next_deadline > .25:
            self._next_deadline = now
        if self._closed.is_set():
            return False, None
        self._next_deadline += 1.0 / self._fps
        ok, frame = self.cap.read()
        if ok:
            return True, frame
        if self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return self.cap.read()
        return False, None

    def close(self) -> None:
        self._closed.set()
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class CaptureEngine:
    def __init__(self, camera_config: CameraConfig, buffer_config: BufferConfig, ring_buffer: TimeRingBuffer, *, buffer_enabled: bool = True) -> None:
        self.camera_config, self.buffer_config, self.ring_buffer = camera_config, buffer_config, ring_buffer
        self.buffer_enabled = bool(buffer_enabled)
        self._packet_listener: Callable[[FramePacket], None] | None = None
        self.latest = LatestFrameStore()
        self._raw_queue: Queue[tuple[int, int, int, np.ndarray]] = Queue(maxsize=buffer_config.encoder_queue_size)
        self._stop_event = Event()
        self._capture_thread: Thread | None = None
        self._encoder_thread: Thread | None = None
        self._source_lock = Lock()
        self._current_source: VideoSource | None = None
        self._stats_lock = Lock()
        self._captured_frames = self._encoded_frames = self._queue_drops = 0
        self._read_failures = self._encode_failures = 0
        self._capture_fps = self._encode_fps = self._average_encode_ms = 0.0
        self._source_description = "Disconnected"
        self._last_error = ""
        self._capture_times: deque[float] = deque()
        self._encode_times: deque[float] = deque()
        self._encode_duration_sum_ms = 0.0
        self._logger = logging.getLogger("long_jump_replay.capture")

    def set_buffer_enabled(self, enabled: bool) -> None:
        self.buffer_enabled = bool(enabled)

    def set_packet_listener(self, listener: Callable[[FramePacket], None] | None) -> None:
        self._packet_listener = listener

    def _make_source(self) -> VideoSource:
        if self.camera_config.source_type == "synthetic":
            return SyntheticSource(self.camera_config.width, self.camera_config.height, self.camera_config.fps)
        if self.camera_config.source_type == "file":
            return VideoFileSource(self.camera_config.file_path, self.camera_config.loop_file)
        return OpenCVCameraSource(self.camera_config)

    @property
    def is_running(self) -> bool:
        return bool(self._capture_thread and self._capture_thread.is_alive())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._capture_thread = Thread(target=self._capture_loop, name="capture", daemon=True)
        self._encoder_thread = Thread(target=self._encoder_loop, name="jpeg-encoder", daemon=True)
        self._encoder_thread.start()
        self._capture_thread.start()
        self._logger.info("capture_started", extra={"event_data": {"event": "capture_started", "source_type": self.camera_config.source_type}})

    def stop(self, timeout: float = 2.5) -> list[str]:
        """Stop without allowing a broken camera driver to trap the GUI forever."""
        self._stop_event.set()
        with self._source_lock:
            source = self._current_source
        if source is not None:
            try:
                source.close()  # release() usually unblocks DirectShow/MSMF read
            except Exception:
                pass
        # Shutdown is not the time to JPEG-encode a stale queue. Discard queued
        # frames so the encoder thread can leave promptly even on a slower PC.
        while True:
            try:
                self._raw_queue.get_nowait()
                self._raw_queue.task_done()
            except Empty:
                break
        deadline = time.perf_counter() + max(.1, timeout)
        alive: list[str] = []
        for thread in (self._capture_thread, self._encoder_thread):
            if thread and thread.is_alive():
                thread.join(max(0.0, deadline - time.perf_counter()))
                if thread.is_alive():
                    alive.append(thread.name)
        self._logger.info("capture_stopped", extra={"event_data": {"event": "capture_stopped", "alive_workers": alive}})
        return alive

    @staticmethod
    def _rolling_fps(times: deque[float], now: float, window: float = 1.5) -> float:
        times.append(now)
        cutoff = now - window
        while times and times[0] < cutoff:
            times.popleft()
        if len(times) < 2:
            return 0.0
        elapsed = times[-1] - times[0]
        return (len(times) - 1) / elapsed if elapsed > 0 else 0.0

    def _capture_loop(self) -> None:
        capture_index = 0
        while not self._stop_event.is_set():
            source = self._make_source()
            with self._source_lock:
                self._current_source = source
            try:
                source.open()
                with self._stats_lock:
                    self._source_description, self._last_error = source.description, ""
                self._logger.info("camera_opened", extra={"event_data": {"event": "camera_opened", "source": source.description}})
                consecutive_failures = 0
                while not self._stop_event.is_set():
                    ok, frame = source.read()
                    if self._stop_event.is_set():
                        break
                    timestamp_ns = time.monotonic_ns()
                    wall_time_ns = time.time_ns()
                    if not ok or frame is None:
                        consecutive_failures += 1
                        with self._stats_lock:
                            self._read_failures += 1
                        if consecutive_failures >= 30:
                            raise RuntimeError("Camera returned 30 invalid frames in a row.")
                        time.sleep(.002)
                        continue
                    consecutive_failures = 0
                    self.latest.update(frame, timestamp_ns, capture_index)
                    with self._stats_lock:
                        self._captured_frames += 1
                        self._capture_fps = self._rolling_fps(self._capture_times, time.perf_counter())
                    item = (capture_index, timestamp_ns, wall_time_ns, frame)
                    try:
                        self._raw_queue.put_nowait(item)
                    except Full:
                        try:
                            self._raw_queue.get_nowait(); self._raw_queue.task_done()
                        except Empty:
                            pass
                        try:
                            self._raw_queue.put_nowait(item)
                        except Full:
                            pass
                        with self._stats_lock:
                            self._queue_drops += 1
                    capture_index += 1
            except Exception as exc:
                if not self._stop_event.is_set():
                    with self._stats_lock:
                        self._last_error = str(exc)
                        self._source_description = "Reconnecting camera…"
                    self._logger.warning("camera_read_failure", extra={"event_data": {"event": "camera_read_failure", "error": str(exc)}})
            finally:
                try:
                    source.close()
                except Exception:
                    pass
                with self._source_lock:
                    if self._current_source is source:
                        self._current_source = None
            if self._stop_event.is_set() or self.camera_config.source_type != "camera":
                break
            self._stop_event.wait(max(.1, self.camera_config.reconnect_seconds))

    def _encoder_loop(self) -> None:
        params = [cv2.IMWRITE_JPEG_QUALITY, self.buffer_config.jpeg_quality]
        nth = self.buffer_config.store_every_nth_frame
        while not self._stop_event.is_set() or not self._raw_queue.empty():
            try:
                capture_index, timestamp_ns, wall_time_ns, frame = self._raw_queue.get(timeout=.1)
            except Empty:
                continue
            try:
                if capture_index % nth != 0:
                    continue
                started = time.perf_counter()
                ok, encoded = cv2.imencode(".jpg", frame, params)
                elapsed_ms = (time.perf_counter() - started) * 1000
                if not ok:
                    with self._stats_lock: self._encode_failures += 1
                    continue
                height, width = frame.shape[:2]
                jpeg = encoded.tobytes()
                packet = FramePacket(0, timestamp_ns, jpeg, width, height, wall_time_ns)
                if self.buffer_enabled:
                    packet = self.ring_buffer.append(timestamp_ns, jpeg, width, height, wall_time_ns)
                listener = self._packet_listener
                if listener is not None:
                    listener(packet)
                with self._stats_lock:
                    self._encoded_frames += 1
                    self._encode_duration_sum_ms += elapsed_ms
                    self._average_encode_ms = self._encode_duration_sum_ms / self._encoded_frames
                    self._encode_fps = self._rolling_fps(self._encode_times, time.perf_counter())
            except Exception as exc:
                with self._stats_lock:
                    self._encode_failures += 1
                    self._last_error = f"JPEG encoder error: {exc}"
            finally:
                self._raw_queue.task_done()

    def stats(self) -> CaptureStats:
        with self._stats_lock:
            return CaptureStats(
                self._captured_frames, self._encoded_frames, self._capture_fps, self._encode_fps,
                self._queue_drops, self._read_failures, self._encode_failures,
                self._average_encode_ms, self._raw_queue.qsize(), self._source_description, self._last_error,
            )
