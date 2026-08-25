from src.progress import ProgressController, ProgressState


def test_determinate_progress_is_monotonic_and_not_complete_early():
    progress = ProgressController("Loading…")
    assert progress.update(completed_units=3, total_units=10).completed_units == 3
    assert progress.update(completed_units=2, total_units=10).completed_units == 3
    assert progress.update(completed_units=10, total_units=10).completed_units == 9
    completed = progress.update(completed_units=10, total_units=10, state=ProgressState.COMPLETED)
    assert completed.completed_units == completed.total_units == 10


def test_progress_supports_indeterminate_paused_blocked_and_failed_states():
    progress = ProgressController("Working…")
    for state in (ProgressState.INDETERMINATE, ProgressState.PAUSED, ProgressState.BLOCKED, ProgressState.FAILED):
        assert progress.update(state=state).state is state
