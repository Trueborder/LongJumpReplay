# Long Jump Replay 2.3

A Windows-oriented live replay application for reviewing long-jump take-off-board decisions. It keeps a rolling live buffer, freezes attempts without stopping capture, preserves attempts as temporary MP4 sessions, supports frame-by-frame ShuttleXpress control, and can optionally manage athletes and rounds.

> This is an operator-assistance prototype, not a certified measuring or officiating system. Test the complete camera, computer, USB connection, lighting, and calibration before an event.

## Main workflow

1. Start the camera or use the synthetic source.
2. Press **Space** to Freeze.
3. Review with Left/Right or the Shuttle jog wheel.
4. Optionally mark **Valid**, **Foul**, or **Review**.
5. Press **Space** again to return Live.
6. By default, an unjudged attempt remains **Not decided** and does not block the next athlete.

Strict judging is optional in **Settings → Attempts & decisions → Require a decision before continuing**.

## Athlete attempt timer

The far-right header timer is independent of recording and judging. It starts only when the operator clicks it or uses the configurable **Start / stop athlete timer** hotkey (unassigned by default).

- `READY 01:00` blinks until explicitly started.
- Clicking while running stops the current value; clicking while stopped or expired restarts the full countdown.
- The final ten seconds are amber, and expiry shows `00:00` in red without sound or an automatic result.
- A successful Freeze stops a running timer. A failed Freeze leaves it running.
- Returning from Replay to Live, manually changing athlete, or applying a new duration resets it to READY.
- The duration is configurable from 1 to 600 seconds in **Settings > Attempts & decisions**.

The timer is available in competition and judge-only modes and is never written into attempt metadata, evidence, or exports.

## What is new in 2.3

- Remade judge-station interface with clearer workflow zones and larger primary actions.
- Task-grouped, card-based Settings workspace with active navigation and clearer descriptions.
- Rebuilt layered timeline with a fixed focus band, stronger Freeze/playhead hierarchy, and interaction guidance.
- Bounded partial post-roll recovery when capture stalls, stricter configuration validation, and consistent Live transitions.
- Optional judging with Not decided as the default result.
- Correct round-by-round athlete rotation.
- Qualification plus an optional manually selected final round.
- Athlete × attempt competition board.
- Start Competition Wizard.
- Complete judge-only mode with competition management disabled.
- Configurable operator-controlled athlete attempt countdown in the header.
- English and Czech interface.
- Remade Settings window with a permanently visible Apply footer.
- Performance presets and impact labels.
- Static, throttled File/View/Help menus for better responsiveness.
- Improved dark-theme inputs and dropdowns.
- Optional recovery, event export, special statuses, operator mode, keyboard controls, next-athlete overlay, and camera diagnostics.

## Competition order

For eight athletes and three qualification attempts, the order is:

```text
Round 1: 1, 2, 3, 4, 5, 6, 7, 8
Round 2: 1, 2, 3, 4, 5, 6, 7, 8
Round 3: 1, 2, 3, 4, 5, 6, 7, 8
```

The final round can advance 8, 10, 12, or a custom number of athletes and add three attempts by default. Finalists are selected manually because the application does not measure jump distances.

## Competition board symbols

| Symbol | Meaning |
|---|---|
| `✓` | Valid |
| `×` | Foul |
| `?` | Review |
| `●` | Completed / Not decided |
| `–` | Passed |
| `DNS` | Did not start |
| `W` | Withdrawn |
| `↻` | Reattempt |

Colours are deliberately soft and are always accompanied by text or symbols.

## Performance presets

| Preset | Intended use |
|---|---|
| Quiet / Low-power | Older laptops, webcams, lower fan noise |
| Balanced | Recommended default |
| High performance | Powerful computers and faster previews |
| Evidence | Full-resolution display and higher-detail board analysis |
| Custom | Manual control of every value |

Settings that can affect CPU, RAM, fan noise, or UI responsiveness show a **Low / Medium / High / Very high** impact badge. Preview FPS is independent of camera recording FPS.

The most useful controls are:

- preview refresh rate;
- timeline refresh rate;
- preview render scale;
- pause hidden panels;
- reduce work while minimized;
- adaptive performance;
- menu rendering throttle;
- live-buffer duration and RAM limit;
- Take-off Assist analysis width.

## Start Competition Wizard

The wizard configures:

- competition management or judge-only mode;
- language;
- Boys/Girls groups and athlete counts;
- qualification and final attempts;
- optional strict judging;
- camera index, resolution, and requested FPS;
- performance preset;
- live buffer, pre-roll, post-roll, retention, and cache;
- whether old temporary recordings should be cleared.

## Settings categories

1. General
2. Language & appearance
3. Performance
4. Camera
5. Board calibration
6. Competition
7. Athletes & rounds
8. Attempts & decisions
9. Final round
10. Replay & storage
11. Views
12. Take-off Assist
13. Hotkeys
14. ShuttleXpress
15. Recovery & export
16. Advanced

The footer remains fixed on every page:

```text
Restore Defaults                       Apply   Apply & Close   Cancel
```

## Board calibration

The digital take-off line can be moved and rotated. A separate board ROI can be drawn for Board Detail and Take-off Assist.

- drag the line centre to move it;
- drag the yellow handle to rotate it;
- Ctrl + mouse wheel fine-rotates the line;
- Shift-drag creates a board ROI;
- drag the ROI or its corner to reposition/resize it.

Take-off Assist only locates a likely local movement peak in the ROI. It never decides Valid or Foul.

## ShuttleXpress defaults

| Control | Default action |
|---|---|
| Jog wheel | Previous / next frame |
| Outer shuttle ring | Previous / next recording |
| Button 1 | Freeze / Live |
| Button 2 | Return Live |
| Button 3 | Valid |
| Button 4 | Foul |
| Button 5 | Review |

All button actions and keyboard shortcuts are configurable.

## Clear temporary recordings

The main-screen button offers:

- Clear everything;
- Clear live buffer only;
- Clear unresolved recordings.

Exported MP4 files and evidence images are not deleted.

## Run from source on Windows

1. Install Python 3.12 x64.
2. Run `INSTALL_WINDOWS.bat`.
3. Run `SELF_TEST.bat`.
4. Run `RUN_SYNTHETIC.bat`.
5. Run `RUN_CAMERA.bat` after selecting/testing the camera.

## Build a portable Windows application

Run:

```text
BUILD_PORTABLE.bat
```

The builder:

- creates an isolated Python environment;
- installs dependencies;
- runs the complete test suite;
- runs the 120 FPS source self-test;
- builds the Windows application with PyInstaller;
- runs the self-test on the packaged EXE;
- creates a ZIP and SHA-256 checksum.

Output:

```text
release\LongJumpReplay-2.3-Windows-x64.zip
```

The recipient only extracts the ZIP and runs `LongJumpReplay.exe`.

A single-file build is available through `BUILD_SINGLE_EXE.bat`, but the portable folder build is recommended for faster startup, easier diagnostics, and fewer antivirus false positives.

## Testing performed in this package

- 43 automated tests;
- synthetic 120 FPS full pipeline self-test;
- 1280 × 720 at 120 FPS soak test;
- temporary MP4 creation and readback;
- clean worker shutdown;
- optional-judging GUI workflow;
- strict-judging workflow;
- round rotation and final round;
- fixed Settings footer across all pages;
- static header menu throttling;
- dark and light visual inspection.

See `TEST_REPORT_2.3.md` for exact results.

## Continue development with Codex

For a complete Windows/Codex handoff, start with `CODEX_START_HERE.md`, `AGENTS.md`, and `PROJECT.KNOWLEDGE.md`.
