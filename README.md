# Long Jump Replay 3.1

## Quick operator guide

Long Jump Replay is a live-review station for long-jump take-off decisions. It keeps capture running continuously, stores a rolling live buffer, and lets an operator freeze an attempt without interrupting the camera.

### The judging loop

1. Watch the live preview and press **Space** or **Freeze**.
2. Review the pinned attempt with **Left/Right**, the timeline, or ShuttleXpress.
3. Optionally choose **Valid**, **Foul**, **Review**, or leave it **Not decided**.
4. Press **Space** again to return to Live. The next athlete can continue by default even when no verdict was entered.

The **Export**, **Delete**, and **Clear all temporary recordings** actions sit together below the recordings list. They affect temporary/cache data only; exported MP4 files and evidence images are preserved.

### Settings that belong on the main video

Settings is organised by task and explains terms such as **Buffer** (recent camera frames kept in RAM), **ROI** (the image area analysed for take-off motion), **FPS** (frames per second), **Codec** (the video storage format), and **HID** (direct USB-controller communication).

Use **View → Board calibration** for visual calibration: drag the line centre to move it, drag the yellow handle to rotate it, and Shift-drag the ROI. Position and size fields are not duplicated in Settings because the video is the reliable place to calibrate them. Line visibility, ROI visibility, and line width remain available in Settings.

### Performance profiles

Choose a profile on Settings → Performance:

- **Quiet** reduces preview work for older or quieter machines.
- **Balanced** is the recommended starting point.
- **High** keeps the interface more fluid on powerful machines.
- **Evidence focus** gives board/analysis work more headroom.
- **Custom** leaves the individual controls under operator control.

Selecting a profile fills the controls below it; **Apply** saves the selected values. These profiles change presentation and analysis workload, not camera FPS or evidence quality. **Older PC mode** is separate and explicit: it retains every second source frame, shortens the live buffer, and is intended only when the operator accepts that trade-off.

### Dark mode and popups

All application-owned dialogs, confirmations, menus, and combobox popups follow the selected light/dark theme. If a dialog is opened during a theme change, close and reopen it to refresh its title and content labels.

### Hotkeys

Settings → Hotkeys puts **Defaults** at the top. Double-click a row to change one shortcut; right-click a row to restore that row. Space always controls Freeze/Live, even when another button has focus.

## Reliability instrumentation and native migration preview

The production application remains the verified Python 3.12/Tkinter/OpenCV build. It now writes a bounded structured runtime log to `LongJumpReplay-runtime.jsonl` beside the active configuration and shows UI tick average, p95, maximum, stall count, and uptime in Help > Diagnostics. Camera start/open/reconnect/stop, Freeze, decision, Live, system pause, shutdown, worker exceptions, and fatal startup failures are recorded without adding data to attempt metadata or evidence.

Run the repeatable 30-second synthetic capture gate with `RUN_STABILITY_CHECK.bat`. The JSON report checks measured capture rate, queue drops, encoder failures, live-buffer statistics, and remaining workers.

An incremental Windows-native preview lives in `native/` and targets .NET 10 WPF. It contains separated Core, Windows Video, Infrastructure, App, and Tests projects; English/Czech preview text; a synthetic camera; bounded Live/Freeze/Replay buffering; frame stepping; camera pause/resume; compatible config reading; bounded shutdown; and a selectable Media Foundation source with friendly-name enumeration and real-time BGRA frames. Launch it with `RUN_NATIVE_PREVIEW.bat`, or create a runtime-independent Windows x64 folder with `BUILD_NATIVE_PREVIEW.bat`. The preview starts synthetically and offers discovered cameras in its source list, with safe synthetic fallback after an open failure. Mode negotiation/reconnect, hardware validation, MP4 evidence, competition workflows, full settings, HID, and exports must reach parity before cutover. Continue using `scripts\run\RUN_CAMERA.bat` for real judging and camera work.

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

The main header also contains a visible **Pause system** switch. Pausing releases the camera, stops live recording, empties the live RAM buffer, blocks judging controls and timer starts, and creates no new temporary attempt cache. Completed attempts already in the session remain available. **Resume system** reconnects the configured camera and starts with a fresh live buffer.

- `READY 01:00` blinks until explicitly started.
- Clicking while running stops the current value; clicking while stopped or expired restarts the full countdown.
- The final ten seconds are amber, and expiry shows `00:00` in red without sound or an automatic result.
- A successful Freeze stops a running timer. A failed Freeze leaves it running.
- Returning from Replay to Live, manually changing athlete, or applying a new duration resets it to READY.
- The duration is configurable from 1 to 600 seconds in **Settings > Attempts & decisions**.

The timer is available in competition and judge-only modes and is never written into attempt metadata, evidence, or exports.

## What is new in 3.1

- Remade judge-station interface with clearer workflow zones and larger primary actions.
- Task-grouped, card-based Settings workspace with active navigation and clearer descriptions.
- Rebuilt layered timeline with a fixed focus band, stronger Freeze/playhead hierarchy, and interaction guidance.
- Bounded partial post-roll recovery when capture stalls, stricter configuration validation, and consistent Live transitions.
- Optional judging with Not decided as the default result.
- Correct round-by-round athlete rotation.
- Qualification plus an optional manually selected final round.
- Athlete × attempt competition board.
- Context-aware arrow-key board navigation, Enter activation, and a right-click menu for changing or deleting recorded attempts; Space remains Freeze/Live.
- Start Competition Wizard.
- Complete judge-only mode with competition management disabled.
- Configurable operator-controlled athlete attempt countdown in the header.
- English and Czech interface.
- Remade Settings window with a permanently visible Apply footer.
- Performance presets and impact labels.
- Static, throttled File/View/Help menus for better responsiveness.
- Improved dark-theme inputs and dropdowns.
- Compact pill-shaped buttons/dropdowns and circular checkboxes throughout both themes.
- Optional recovery, event export, special statuses, operator mode, keyboard controls, next-athlete overlay, and camera diagnostics.

## Competition order

The next-attempt strip is shown directly above the Competition Board. While that tab is selected, plain arrow keys move between cells regardless of which board control has focus and do not step replay frames. Press Enter to open or select the focused cell; Space remains Freeze/Live. During Freeze, the blue box remains on the attempt being judged and advances only after returning Live. Right-click a recorded or eligible blank cell to mark Not decided, Valid, Foul, Review, Passed, Missing, or Withdrawn. A blank-cell result is stored without video; deletion becomes available once that cell has a record.

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

For older or resource-constrained PCs, choose **Older PC mode** on the Performance settings page. This explicit mode keeps camera capture at the configured rate, renders the interface at 20 Hz, retains every second camera frame (60 FPS from a 120 FPS camera), uses a 15-second live buffer, and limits its RAM budget to 1 GB.

The most useful controls are:

- preview refresh rate;
- timeline refresh rate;
- preview render scale;
- pause hidden panels;
- reduce work while minimized;
- adaptive performance;
- menu rendering throttle;
- live-buffer duration and RAM limit;

The Camera settings page lists friendly Windows device names in a read-only dropdown, for example `0 · Integrated Camera` or `1 · OBS Virtual Camera`. The leading number remains the OpenCV camera index stored in the configuration. Reopen Settings to rescan devices connected after the window was opened, and restart the app after changing the camera.
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
2. Run `scripts\setup\INSTALL_WINDOWS.bat`.
3. Run `SELF_TEST.bat`.
4. Run `scripts\run\RUN_SYNTHETIC.bat`.
5. Run `scripts\run\RUN_CAMERA.bat` after selecting/testing the camera.

## Build a portable Windows application

For the complete customer-facing release, run:

```text
BUILD_CUSTOMER_RELEASE.bat
```

This is the primary one-click release command. After source tests and frozen self-tests pass, it replaces the existing `release` folder and creates:

- `LongJumpReplay-Setup-3.1.exe` and its SHA-256 checksum;
- a deployable `website` folder containing the same installer download;
- customer documentation and a recursive `SHA256SUMS.txt` manifest.

The customer release intentionally excludes the loose application payload, private license key, and owner-only license generator. Run `BUILD_CUSTOMER_RELEASE.bat --no-pause` from automation when no final keypress prompt is wanted.

For the portable fallback package only, run:

```text
scripts\build\BUILD_PORTABLE.bat
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
release\LongJumpReplay-3.1-Windows-x64.zip
```

The recipient only extracts the ZIP and runs `LongJumpReplay.exe`.

A single-file build is available through `BUILD_SINGLE_EXE.bat`, but the portable folder build is recommended for faster startup, easier diagnostics, and fewer antivirus false positives.

## Generate customer license keys

Run `scripts\run\RUN_LICENSE_GENERATOR.bat` on the owner/support computer. Enter the machine code shown by the customer’s first launch, the customer name, and an internal license ID. Use **Generate key**, then **Copy key** or **Save key…** and send only the resulting `LJR2...` key to the customer.

The optional `scripts\build\BUILD_LICENSE_GENERATOR.bat` creates an admin-only GUI EXE under `release\LongJumpReplay-License-Generator`. It reads the private signing key from `tools\.license_private_key.json`; never distribute that file or the generator with customer software. See `docs\LICENSE_ADMIN.md` for the operating procedure.

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

See `TEST_REPORT_3.1.md` for exact results.

## Continue development with Codex

For a complete Windows/Codex handoff, start with `AGENTS.md`, `PROJECT.KNOWLEDGE.md`, and `docs/development/WINDOWS_CODEX_SETUP.md`.
