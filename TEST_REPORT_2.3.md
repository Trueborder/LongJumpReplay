# Long Jump Replay 2.3 — Test Report

Test date: 3 August 2026

## Result summary

- Automated test suite: **43 passed**
- Synthetic end-to-end self-test: **PASS**
- 1280×720 at 120 fps soak test: **PASS**
- Queue drops in the soak test: **0**
- JPEG encode failures in the soak test: **0**
- Remaining application worker threads after shutdown: **none**

## Automated regression suite

Command:

```bash
xvfb-run -a pytest -o addopts='' -q
```

Result:

```text
43 passed in 17.69s
```

The suite covers:

- ring-buffer retention and memory limits;
- capture, JPEG encoding and frame lookup;
- attempt pinning, post-roll collection, temporary MP4 creation and export;
- clean shutdown during Live, Freeze and background encoding;
- fixed-playhead timeline behaviour and pooled Canvas items;
- video-canvas calibration, ROI and frame comparison;
- Take-off Assist candidate detection;
- hotkeys, focus handling and Shuttle action dispatch;
- athlete rotation by rounds;
- individual attempt limits;
- manual finalists and three additional final attempts;
- optional judging with **Not decided** as the default;
- strict decision-required mode;
- the exact workflow `Freeze → Live without verdict → next athlete → Freeze`;
- judge-only mode with competition controls hidden;
- competition board and attempt selection;
- all 16 Settings pages;
- fixed Settings footer with Apply and Apply & Close visible on every page;
- static File/View/Help menus and redraw throttling while a menu is open.

## Critical no-verdict workflow

A dedicated GUI test performs this sequence:

1. Athlete 1 is frozen.
2. The same Freeze/Live action returns to Live without selecting Valid, Foul or Review.
3. Athlete 1 remains stored as **Not decided**.
4. The roster advances to Athlete 2.
5. A second Freeze immediately creates Athlete 2's recording.

Verified result:

```text
Athlete after first recording: 2
Temporary recordings: 2
First decision: Not decided
First roster slot completed: yes
Second recording assigned to athlete: 2
```

## Static menu responsiveness test

The header menu is created once and is not rebuilt by the video update loop. While a menu is open, expensive preview rendering is temporarily capped at 15 Hz while capture and recording continue normally.

Verified:

```text
Menu object unchanged across repeated GUI ticks: yes
Menu-active preview limit: <= 15 Hz
Camera capture stopped by menu: no
```

## End-to-end synthetic self-test

Command:

```bash
python app.py --self-test --self-test-report SELF_TEST_RESULT_2.3.txt
```

Result:

```text
Capture: 120.0 fps
JPEG buffer: 120.0 fps
Live buffer: 192 frames
Queue drops: 0
Temporary MP4: 180 frames at 120.0 fps
Export: MP4 created
Remaining workers: none
SELF-TEST: OK
```

## 1280×720 / 120 fps soak test

Synthetic scene, full capture and JPEG-buffer path:

```text
Capture: 120.01 fps
JPEG buffer: 120.07 fps
Queue drops: 0
Encode failures: 0
Average JPEG encode: 1.585 ms
Live buffer: 480 frames / 3.99 s / 22.14 MiB
Temporary MP4: 300 frames
Remaining workers: none
SOAK TEST: OK
```

This result is for the synthetic source in the test environment. A physical camera can behave differently depending on its driver, USB controller, exposure, codec and supported capture modes.

## Visual checks

Manually inspected in both light and dark themes:

- new competition header and judge-only mode;
- competition board with subtle status colours;
- Settings navigation and fixed footer;
- performance impact badges;
- dark combobox, popup-list, entry, selection and disabled-state contrast;
- English and Czech interface labels;
- fixed-playhead timeline;
- board-detail layout and rotated board guide.

Screenshots are included under `docs/screenshots`.

## Packaging checks

The project contains:

- `BUILD_PORTABLE.bat` for the recommended shareable Windows folder/ZIP;
- `BUILD_SINGLE_EXE.bat` for a one-file build;
- a PyInstaller specification;
- a Windows GitHub Actions build workflow;
- source and frozen-application self-tests that run before release packaging.

## Environment limitations

The development environment used for this report is Linux. Therefore these items were **not** claimed as physically tested here:

- a real Windows 11 `.exe` build;
- DirectShow or Media Foundation with a physical camera;
- a real 120 fps USB camera;
- direct HID communication with a physical Contour ShuttleXpress;
- Windows title-bar dragging and native device-driver behaviour.

The Windows builder is designed to compile the application on Windows, run the automated suite, run the source self-test, build the executable, and then run the self-test again against the packaged executable. A real camera and ShuttleXpress should still be tested on the exact competition laptop before official use.

## Safety and intended use

Long Jump Replay remains an experimental decision-support application, not a certified World Athletics measurement or officiating device. The human judge remains responsible for the decision.
