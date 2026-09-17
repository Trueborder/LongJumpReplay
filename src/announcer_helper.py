from __future__ import annotations

from .adjudication import AthleteContext


def announcer_athlete_name(athlete: AthleteContext, language: str) -> str:
    """Return a short, unambiguous name suitable for an announcer prompt."""
    full_name = " ".join(str(athlete.name or "").strip().split())
    if full_name:
        if "," in full_name:
            surname = full_name.split(",", 1)[0].strip()
        else:
            surname = full_name.rsplit(" ", 1)[-1]
        if surname:
            return surname.upper()

    number = str(athlete.bib or athlete.competitor_number or "?").strip()
    prefix = "ZÁVODNÍK" if language == "cs" else "ATHLETE"
    return f"{prefix} #{number}"
