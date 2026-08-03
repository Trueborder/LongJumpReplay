# Testing and release guide

## Fast checks

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run one file:

```powershell
python -m pytest tests\test_competition_23.py -q
```

Run one test:

```powershell
python -m pytest tests\test_main_window_23_gui.py::test_not_decided_attempt_does_not_block_next_freeze -q
```

## Full development gate

```powershell
.\RUN_DEVELOPMENT_CHECKS.ps1
```

This runs:

1. full pytest suite;
2. synthetic pipeline self-test;
3. optional syntax compilation.

## Manual GUI smoke test

Run:

```powershell
python app.py --synthetic --windowed
```

Check:

- Space Freeze/Live after clicking multiple buttons;
- Not decided advances correctly;
- strict mode blocks correctly;
- frame stepping and Shuttle action queue;
- timeline fixed playhead and smooth dragging;
- window move/resize;
- File/View/Help responsiveness;
- dark and light settings comboboxes;
- Settings Apply footer on every page;
- competition board updates;
- guide rotation and ROI;
- clear-cache modes;
- close during Live and attempt encoding.

## Real hardware gate

Before event use, validate on the exact setup:

- camera;
- lens/field of view;
- USB port and cable;
- selected capture backend;
- requested and actual FPS;
- lighting and exposure;
- laptop power profile;
- ShuttleXpress and vendor driver;
- disk free space;
- portable EXE build.

## Release build

```powershell
.\BUILD_PORTABLE.bat
```

Do not distribute until the frozen self-test passes and the ZIP has been extracted and launched from a clean directory.

## Version updates

Search for the old version string before release:

```powershell
rg "2\.3|LongJumpReplay-2\.3"
```

Update consistently:

- README files;
- changelog/test report;
- build scripts;
- GitHub workflow artifact names;
- `windows_version_info.txt`;
- PyInstaller spec if applicable;
- release filenames.
