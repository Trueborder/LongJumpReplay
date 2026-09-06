"""Generate the clean configuration embedded in customer builds."""

from __future__ import annotations

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from src.config import AppConfig, save_config  # noqa: E402


def main() -> None:
    destination = REPOSITORY_ROOT / "packaging" / "generated" / "config.json"
    config = AppConfig()
    config.general.onboarding_completed = False
    config.general.recording_mode_prompted = False
    save_config(config, destination)


if __name__ == "__main__":
    main()
