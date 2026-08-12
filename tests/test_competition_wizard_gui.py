import tkinter as tk

from src.competition_setup import WizardReadiness
from src.competition_wizard import CompetitionWizard
from src.config import AppConfig
from src.theme import ThemeManager


def _ready(recordings: int = 0, language: str = "en") -> WizardReadiness:
    return WizardReadiness(language, True, 120, 60.0, 60.0, "Synthetic source", "", 90, 1.5, 0, 1024**3, recordings)


def test_wizard_opens_directly_in_competition_setup() -> None:
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    finished = []
    wizard = CompetitionWizard(root, AppConfig(), lambda *args: finished.append(args), readiness_provider=_ready)
    wizard.update_idletasks()
    assert wizard.setup_index == 0
    assert wizard.minsize() == (1000, 660)
    assert not hasattr(wizard, "COACH_STEPS")
    assert not hasattr(wizard, "_render_learn")
    assert finished == []

    wizard._choose_template("final")
    assert wizard.model.competition.final_round_enabled
    wizard._close(); root.destroy()


def test_wizard_requires_recording_disposition_and_finishes_competition_only() -> None:
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("light")
    finished = []
    wizard = CompetitionWizard(root, AppConfig(), lambda *args: finished.append(args), readiness_provider=lambda: _ready(3))
    wizard.setup_index = 4; wizard._render(); wizard.update_idletasks()
    wizard._setup_next()
    assert not finished
    assert wizard.error_var.get()
    wizard.recording_disposition.set("keep")
    wizard._setup_next()
    assert len(finished) == 1
    competition, disposition = finished[0]
    assert competition.enabled
    assert not competition.require_decision_before_continue
    assert disposition == "keep"
    root.destroy()


def test_wizard_group_and_final_validation_is_inline() -> None:
    root = tk.Tk(); root.withdraw(); ThemeManager(root).apply("dark")
    wizard = CompetitionWizard(root, AppConfig(), lambda *_args: None, readiness_provider=_ready)
    wizard.setup_index = 1
    wizard.vars["boys"].set(False); wizard.vars["girls"].set(False)
    wizard._setup_next()
    assert wizard.setup_index == 1
    assert "group" in wizard.error_var.get().lower()

    wizard.vars["boys"].set(True); wizard.vars["boys_count"].set("4")
    wizard.vars["final"].set(True); wizard.vars["finalists"].set("8")
    wizard.setup_index = 2
    wizard._setup_next()
    assert wizard.setup_index == 2
    assert "Finalists" in wizard.error_var.get()
    wizard._close(); root.destroy()
