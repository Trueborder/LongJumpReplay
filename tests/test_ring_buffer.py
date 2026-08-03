from src.ring_buffer import TimeRingBuffer


def test_time_and_memory_eviction(jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(duration_seconds=1.0, max_memory_mb=128)
    ring.append(0, jpeg, 160, 90)
    ring.append(500_000_000, jpeg, 160, 90)
    ring.append(1_500_000_000, jpeg, 160, 90)
    assert ring.oldest().timestamp_ns == 500_000_000
    assert ring.newest().timestamp_ns == 1_500_000_000


def test_seek_step_and_snapshot(jpeg_frame):
    jpeg, _ = jpeg_frame
    ring = TimeRingBuffer(10, 128)
    packets = [ring.append(i * 100_000_000, jpeg, 160, 90) for i in range(10)]
    assert ring.at_timestamp(450_000_000).seq == packets[4].seq
    assert ring.step(packets[4].seq, 2).seq == packets[6].seq
    snap = ring.snapshot_between(250_000_000, 650_000_000)
    assert [p.seq for p in snap] == [3, 4, 5, 6]
