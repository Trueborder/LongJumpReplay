from src.athlete_timer import AthleteTimerController, AthleteTimerState, format_countdown, format_countdown_tenths


class FakeClock:
    def __init__(self) -> None:
        self.now_ns = 0

    def __call__(self) -> int:
        return self.now_ns

    def advance(self, seconds: float) -> None:
        self.now_ns += int(seconds * 1_000_000_000)


def test_countdown_uses_monotonic_elapsed_time_and_rounds_up():
    clock = FakeClock()
    timer = AthleteTimerController(60, clock)
    timer.start()
    clock.advance(0.001)
    assert timer.snapshot().remaining_seconds == 60
    assert timer.snapshot().remaining_tenths == 600
    clock.advance(0.999)
    assert timer.snapshot().remaining_seconds == 59
    assert timer.snapshot().remaining_tenths == 590
    clock.advance(48.1)
    assert timer.snapshot().remaining_seconds == 11


def test_stop_expiry_restart_and_reset():
    clock = FakeClock()
    timer = AthleteTimerController(12, clock)
    timer.start(); clock.advance(2.2)
    stopped = timer.stop()
    assert stopped.state is AthleteTimerState.STOPPED
    assert stopped.remaining_seconds == 10
    clock.advance(20)
    assert timer.snapshot().remaining_seconds == 10

    timer.start()
    assert timer.snapshot().remaining_seconds == 12
    clock.advance(12)
    assert timer.snapshot().state is AthleteTimerState.EXPIRED
    assert timer.snapshot().remaining_seconds == 0

    timer.start()
    assert timer.snapshot().remaining_seconds == 12
    assert timer.reset().state is AthleteTimerState.READY
    assert timer.snapshot().remaining_seconds == 12


def test_duration_change_resets_full_ready_value():
    timer = AthleteTimerController(60, FakeClock())
    timer.start()
    snapshot = timer.set_duration(90)
    assert snapshot.state is AthleteTimerState.READY
    assert snapshot.remaining_seconds == 90
    assert format_countdown(90) == "01:30"
    assert format_countdown_tenths(905) == "01:30.5"
