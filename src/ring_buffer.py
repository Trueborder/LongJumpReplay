from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import OrderedDict
from threading import RLock
from typing import Iterable

from .models import BufferStats, FramePacket


class TimeRingBuffer:
    """Thread-safe time-based ring buffer of JPEG-compressed frames."""

    def __init__(self, duration_seconds: float, max_memory_mb: int) -> None:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if max_memory_mb <= 0:
            raise ValueError("max_memory_mb must be positive")
        self._duration_ns = int(duration_seconds * 1_000_000_000)
        self._max_memory_bytes = int(max_memory_mb * 1024 * 1024)
        self._packets: OrderedDict[int, FramePacket] = OrderedDict()
        self._timestamps: list[int] = []
        self._sequences: list[int] = []
        self._memory_bytes = 0
        self._next_seq = 0
        self._lock = RLock()

    def append(self, timestamp_ns: int, jpeg: bytes, width: int, height: int, wall_time_ns: int = 0) -> FramePacket:
        if not jpeg:
            raise ValueError("JPEG data cannot be empty")
        with self._lock:
            packet = FramePacket(self._next_seq, timestamp_ns, bytes(jpeg), width, height, wall_time_ns)
            self._next_seq += 1
            self._packets[packet.seq] = packet
            self._timestamps.append(timestamp_ns)
            self._sequences.append(packet.seq)
            self._memory_bytes += packet.size_bytes
            self._evict_locked(timestamp_ns)
            return packet

    def _evict_locked(self, newest_timestamp_ns: int) -> None:
        cutoff = newest_timestamp_ns - self._duration_ns
        removed_count = 0
        while self._packets:
            oldest = next(iter(self._packets.values()))
            if oldest.timestamp_ns >= cutoff and self._memory_bytes <= self._max_memory_bytes:
                break
            _, removed = self._packets.popitem(last=False)
            self._memory_bytes -= removed.size_bytes
            removed_count += 1
        if removed_count:
            del self._timestamps[:removed_count]
            del self._sequences[:removed_count]

    def clear(self) -> None:
        with self._lock:
            self._packets.clear()
            self._timestamps.clear()
            self._sequences.clear()
            self._memory_bytes = 0

    def get(self, seq: int | None) -> FramePacket | None:
        if seq is None:
            return None
        with self._lock:
            return self._packets.get(seq)

    def oldest(self) -> FramePacket | None:
        with self._lock:
            return next(iter(self._packets.values()), None)

    def newest(self) -> FramePacket | None:
        with self._lock:
            return next(reversed(self._packets.values()), None) if self._packets else None

    def step(self, seq: int | None, delta: int) -> FramePacket | None:
        with self._lock:
            if not self._sequences:
                return None
            if seq is None:
                index = len(self._sequences) - 1
            else:
                index = bisect_left(self._sequences, seq)
                if index >= len(self._sequences):
                    index = len(self._sequences) - 1
                elif self._sequences[index] != seq and index > 0:
                    left = self._sequences[index - 1]
                    right = self._sequences[index]
                    if abs(seq - left) <= abs(right - seq):
                        index -= 1
            index = max(0, min(len(self._sequences) - 1, index + delta))
            return self._packets[self._sequences[index]]

    def at_timestamp(self, timestamp_ns: int) -> FramePacket | None:
        with self._lock:
            if not self._timestamps:
                return None
            index = bisect_right(self._timestamps, timestamp_ns) - 1
            index = max(0, min(len(self._timestamps) - 1, index))
            return self._packets[self._sequences[index]]

    def seconds_before_newest(self, seconds: float) -> FramePacket | None:
        with self._lock:
            if not self._timestamps:
                return None
            target = self._timestamps[-1] - int(max(0.0, seconds) * 1_000_000_000)
        return self.at_timestamp(target)

    def relative_offset_seconds(self, seq: int | None) -> float:
        with self._lock:
            if not self._packets or seq is None or seq not in self._packets:
                return 0.0
            return (self._packets[seq].timestamp_ns - self._timestamps[-1]) / 1_000_000_000

    def snapshot_between(self, start_ns: int, end_ns: int) -> list[FramePacket]:
        if end_ns < start_ns:
            start_ns, end_ns = end_ns, start_ns
        with self._lock:
            left = bisect_left(self._timestamps, start_ns)
            right = bisect_right(self._timestamps, end_ns)
            seqs = self._sequences[left:right]
            return [self._packets[seq] for seq in seqs]

    def snapshot_around(self, seq: int, pre_seconds: float, post_seconds: float) -> list[FramePacket]:
        with self._lock:
            selected = self._packets.get(seq)
            if selected is None:
                return []
            start = selected.timestamp_ns - int(max(0.0, pre_seconds) * 1_000_000_000)
            end = selected.timestamp_ns + int(max(0.0, post_seconds) * 1_000_000_000)
        return self.snapshot_between(start, end)

    def all_packets(self) -> list[FramePacket]:
        with self._lock:
            return list(self._packets.values())

    def stats(self) -> BufferStats:
        with self._lock:
            if not self._packets:
                return BufferStats(0, 0.0, 0, None, None)
            duration = (self._timestamps[-1] - self._timestamps[0]) / 1_000_000_000
            return BufferStats(
                len(self._packets), max(0.0, duration), self._memory_bytes,
                self._sequences[0], self._sequences[-1],
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._packets)

    def __iter__(self) -> Iterable[FramePacket]:
        return iter(self.all_packets())
