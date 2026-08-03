from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .attempts import AttemptManager
from .exporter import decode_packet
from .models import MediaFrame
from .ring_buffer import TimeRingBuffer


class PlaybackMode(str, Enum):
    LIVE = "LIVE"
    LIVE_BUFFER = "LIVE_BUFFER"
    ATTEMPT = "ATTEMPT"


@dataclass(slots=True)
class PlaybackController:
    ring_buffer: TimeRingBuffer
    attempts: AttemptManager
    mode: PlaybackMode = PlaybackMode.LIVE
    live_seq: int | None = None
    attempt_id: int | None = None
    attempt_frame_index: int = 0

    def go_live(self) -> None:
        self.attempts.clear_selection()
        self.mode = PlaybackMode.LIVE
        newest = self.ring_buffer.newest()
        self.live_seq = newest.seq if newest else None
        self.attempt_id = None

    def freeze_to_new_attempt(
        self,
        competitor_group: str = "",
        competitor_number: int = 0,
        competitor_attempt_number: int = 0,
        quality_warning: str = "",
        competition_phase: str = "qualification",
    ) -> int | None:
        newest = self.ring_buffer.newest()
        if newest is None:
            return None
        attempt = self.attempts.create_attempt(
            newest.timestamp_ns,
            competitor_group=competitor_group,
            competitor_number=competitor_number,
            competitor_attempt_number=competitor_attempt_number,
            quality_warning=quality_warning,
            competition_phase=competition_phase,
        )
        if attempt is None:
            return None
        self.mode = PlaybackMode.ATTEMPT
        self.attempt_id = attempt.attempt_id
        self.attempt_frame_index = attempt.freeze_frame_index
        return attempt.attempt_id

    def toggle_freeze(self) -> int | None:
        if self.mode is PlaybackMode.LIVE:
            return self.freeze_to_new_attempt()
        self.go_live()
        return None

    def select_attempt(self, attempt_id: int, at_freeze: bool = True) -> bool:
        attempt = self.attempts.select(attempt_id)
        if attempt is None:
            return False
        self.mode = PlaybackMode.ATTEMPT
        self.attempt_id = attempt_id
        if at_freeze:
            self.attempt_frame_index = attempt.freeze_frame_index
        else:
            self.attempt_frame_index = max(0, min(attempt.frame_count - 1, self.attempt_frame_index))
        return True

    def select_relative_attempt(self, delta: int) -> bool:
        attempt = self.attempts.select_relative(delta)
        return bool(attempt and self.select_attempt(attempt.attempt_id))

    def step(self, delta: int) -> None:
        if self.mode is PlaybackMode.LIVE:
            newest = self.ring_buffer.newest()
            self.mode = PlaybackMode.LIVE_BUFFER
            self.live_seq = newest.seq if newest else None
        if self.mode is PlaybackMode.LIVE_BUFFER:
            packet = self.ring_buffer.step(self.live_seq, delta)
            self.live_seq = packet.seq if packet else None
        elif self.mode is PlaybackMode.ATTEMPT and self.attempt_id is not None:
            count = self.attempts.frame_count(self.attempt_id)
            self.attempt_frame_index = max(0, min(max(0, count - 1), self.attempt_frame_index + delta))

    def seek_timestamp(self, timestamp_ns: int) -> None:
        if self.mode is PlaybackMode.ATTEMPT and self.attempt_id is not None:
            self.attempt_frame_index = self.attempts.frame_index_at_timestamp(self.attempt_id, timestamp_ns)
        else:
            packet = self.ring_buffer.at_timestamp(timestamp_ns)
            if packet:
                self.mode = PlaybackMode.LIVE_BUFFER
                self.live_seq = packet.seq

    def displayed_frame(self) -> MediaFrame:
        if self.mode is PlaybackMode.ATTEMPT and self.attempt_id is not None:
            return self.attempts.get_frame(self.attempt_id, self.attempt_frame_index)
        if self.mode is PlaybackMode.LIVE:
            packet = self.ring_buffer.newest()
            self.live_seq = packet.seq if packet else None
        else:
            packet = self.ring_buffer.get(self.live_seq)
            if packet is None:
                packet = self.ring_buffer.oldest()
                self.live_seq = packet.seq if packet else None
        if packet is None:
            return MediaFrame(None, 0, 0, 0, 0.0)
        frame = decode_packet(packet)
        stats = self.ring_buffer.stats()
        index = max(0, packet.seq - (stats.oldest_seq or packet.seq))
        return MediaFrame(frame, packet.timestamp_ns, index, stats.frame_count, 0.0)
