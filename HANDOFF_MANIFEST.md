# Codex handoff manifest

## Start here

1. `AGENTS.md`
2. `PROJECT.KNOWLEDGE.md`
3. `docs/development/WINDOWS_CODEX_SETUP.md`

## Windows helper scripts

- `TRANSFER_TO_DOCUMENTS.ps1` — safely copy the source into `Documents\LongJumpReplay`
- `SETUP_DEVELOPMENT.ps1` — create `.venv`, install dependencies, run tests/self-test, initialize Git when available
- `INSTALL_CODEX_WINDOWS.ps1` — optional wrapper for the official Codex installer
- `START_CODEX.ps1` — launch Codex in the repository root
- `RUN_DEVELOPMENT_CHECKS.ps1` — compile, test, and self-test
- `CREATE_PROJECT_BACKUP.ps1` — create a clean source backup ZIP

## Development references

- `docs/development/ARCHITECTURE.md`
- `docs/development/TESTING_AND_RELEASE.md`
- `docs/development/CURRENT_BACKLOG.md`

## Existing project documentation

- `README.md`
- `README_CZ.md`
- `CHANGELOG_3.1.md`
- `UPGRADE_2.3.md`

## Validation of this handoff

Before packaging, the source passed:

- 43 pytest tests under a virtual display;
- synthetic 120 FPS pipeline self-test;
- temporary MP4 creation/readback;
- export;
- clean worker shutdown.

Windows-specific scripts and the physical camera/Shuttle path still need to be executed on the target Windows computer.
