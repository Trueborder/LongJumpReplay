from src.competition_setup import CompetitionSetupModel, WizardReadiness, merge_competition_setup
from src.config import AppConfig, CompetitionConfig


def test_templates_are_deterministic_and_preserve_valid_group_counts() -> None:
    model = CompetitionSetupModel(CompetitionConfig(boys_competitors=12, girls_competitors=9))
    model.apply_template("final")
    c = model.competition
    assert c.enabled and c.final_round_enabled
    assert (c.default_attempts_per_competitor, c.finalists_count, c.final_attempts, c.final_order) == (3, 8, 3, "reverse")
    assert (c.boys_competitors, c.girls_competitors) == (12, 9)
    assert not c.require_decision_before_continue
    assert c.next_athlete_overlay and c.show_state_banner

    model.apply_template("judge_only")
    assert not c.enabled
    assert c.final_round_enabled
    model.apply_template("simple")
    assert c.enabled and not c.final_round_enabled


def test_template_repairs_zero_enabled_group_count() -> None:
    model = CompetitionSetupModel(CompetitionConfig(boys_competitors=0, girls_enabled=False))
    model.apply_template("simple")
    assert model.competition.boys_competitors == 8


def test_group_dependencies_and_validation() -> None:
    model = CompetitionSetupModel(CompetitionConfig())
    c = model.competition
    c.boys_enabled = False
    c.active_group = "Boys"
    model.normalize_dependencies()
    assert c.active_group == "Girls"
    c.girls_enabled = False
    assert model.validate_step("groups")["groups"] == "group_required"


def test_finalists_cannot_exceed_smallest_enabled_group() -> None:
    model = CompetitionSetupModel(CompetitionConfig(boys_competitors=12, girls_competitors=6, final_round_enabled=True, finalists_count=8))
    assert model.validate_step("attempts")["finalists"] == "finalists_exceed_group"
    model.competition.finalists_count = 6
    assert model.validate_step("attempts") == {}


def test_expected_attempt_cells_counts_each_enabled_group() -> None:
    model = CompetitionSetupModel(CompetitionConfig(boys_competitors=10, girls_competitors=8, default_attempts_per_competitor=3, final_round_enabled=True, finalists_count=4, final_attempts=2))
    assert model.expected_attempt_cells() == (18 * 3) + (2 * 4 * 2)
    model.apply_template("judge_only")
    assert model.expected_attempt_cells() == 0


def test_readiness_levels_and_issue_thresholds() -> None:
    ready = WizardReadiness("en", True, 100, 60.0, 60.0, "Camera 0", "", 90, 1.5, 20, 100, 2)
    assert ready.level == "ready"
    assert ready.issue_keys() == ()

    warming = WizardReadiness("en", True, 10, 0.0, 60.0, "Camera 0", "", 0, 0.0, 0, 100, 0)
    assert warming.level == "warming"

    disconnected = WizardReadiness("en", True, 0, 0.0, 60.0, "Reconnecting camera…", "Camera unavailable", 0, 0.0, 0, 100, 0)
    assert disconnected.issue_keys() == ("no_video",)

    warning = WizardReadiness("en", True, 100, 40.0, 60.0, "Camera 0", "", 0, 0.0, 85, 100, 0)
    assert warning.level == "warning"
    assert warning.issue_keys() == ("low_fps", "empty_buffer", "cache_high")


def test_merge_preserves_latest_technical_settings_and_resets_competition_progress() -> None:
    current = AppConfig()
    current.camera.device_index = 4
    current.general.language = "cs"
    competition = CompetitionConfig(
        boys_competitors=12,
        current_competitor_by_group={"Boys": 7, "Girls": 3},
        finalist_numbers_by_group={"Boys": [1, 2], "Girls": [4]},
        final_round_started_by_group={"Boys": True, "Girls": True},
    )
    merged = merge_competition_setup(current, competition)
    assert merged.camera.device_index == 4
    assert merged.general.language == "cs"
    assert merged.competition.boys_competitors == 12
    assert merged.competition.current_competitor_by_group == {"Boys": 1, "Girls": 1}
    assert merged.competition.finalist_numbers_by_group == {"Boys": [], "Girls": []}
    assert merged.competition.final_round_started_by_group == {"Boys": False, "Girls": False}
