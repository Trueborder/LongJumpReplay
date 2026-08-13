# Repository Layout Reorganization

## Goal

Make the LongJumpReplay source checkout easier to navigate as a developer workspace by grouping operational scripts, secondary documentation, and packaging metadata while retaining conventional project files at the repository root.

## Scope

Move only files that currently exist in the working tree. Preserve existing staged, unstaged, untracked, and ignored work that is unrelated to this reorganization. In particular, do not modify or reorganize `website/`, generated output directories, virtual environments, runtime data, exports, evidence, screenshots, or release artifacts.

## Target layout

```text
LongJumpReplay/
|-- app.py
|-- README.md
|-- LICENSE.txt
|-- THIRD_PARTY_NOTICES.txt
|-- AGENTS.md
|-- PROJECT.KNOWLEDGE.md
|-- config.json
|-- pytest.ini
|-- requirements.txt
|-- requirements-build.txt
|-- docs/
|   |-- CHANGELOG_3.1.md
|   |-- README_CZ.md
|   |-- RECOMMENDED_SYSTEM_REQUIREMENTS.md
|   `-- development/
|-- packaging/
|   `-- LongJumpReplay.spec
`-- scripts/
    |-- build/
    |   |-- BUILD_LICENSE_GENERATOR.bat
    |   |-- BUILD_PORTABLE.bat
    |   `-- BUILD_RELEASE.bat
    |-- maintenance/
    |   `-- CREATE_PROJECT_BACKUP.ps1
    |-- run/
    |   |-- RUN_CAMERA.bat
    |   |-- RUN_LICENSE_GENERATOR.bat
    |   |-- RUN_SYNTHETIC.bat
    |   `-- RUN_TESTS.bat
    `-- setup/
        |-- INSTALL_CODEX_WINDOWS.ps1
        `-- INSTALL_WINDOWS.bat
```

`windows_version_info.txt` belongs in `packaging/` if it is restored later, but its existing deletion will not be reversed as part of this work. Likewise, previously deleted root scripts will remain deleted.

## Compatibility design

Every moved batch script will derive the repository root from `%~dp0` and change to that absolute directory before reading source files, creating environments, invoking Python, or writing build output. Moved PowerShell scripts will derive the same root from `$PSScriptRoot`. Scripts will call one another through their new absolute paths beneath `scripts/`.

The portable build will invoke `packaging/LongJumpReplay.spec`. The spec will use repository-root-relative source and asset paths while continuing to produce the same `dist/` and `release/` layouts. No Python package imports, runtime configuration paths, or customer output paths will change.

All active references in `README.md`, `docs/`, workflow/build configuration, and `PROJECT.KNOWLEDGE.md` will be updated to the new paths. References that document historical filenames in a changelog may remain historical when changing them would make the record inaccurate.

## Verification

The implementation will verify:

1. no active reference points to an old root-level script, spec, or moved document;
2. each moved script resolves the repository root correctly when launched from another working directory;
3. batch-file syntax and cross-script paths remain coherent through static inspection;
4. `python -m pytest` passes;
5. `python app.py --self-test` passes;
6. Git reports only the intended moves/reference edits plus pre-existing user changes.

The reorganization does not require a GUI launch because it changes developer entry-point paths rather than application UI behavior.

