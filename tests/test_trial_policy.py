from src.trial import TrialStatus, capabilities_for


def test_replay_only_trial_policy_allows_showcase_actions_only():
    policy = capabilities_for(TrialStatus(True, False, 1, 2, 1_700_000_000))

    assert policy.permits("capture")
    assert policy.permits("freeze")
    assert policy.permits("replay")
    assert policy.permits("save_frame")
    assert policy.permits("video_export")
    assert not policy.permits("competition_setup")
    assert not policy.permits("judging")
    assert not policy.permits("evidence_package")


def test_expired_trial_policy_allows_nothing():
    policy = capabilities_for(TrialStatus(False, True, 3, 0, 1_700_000_000, "trial.expired"))

    assert not policy.allowed
    assert not policy.permits("replay")
