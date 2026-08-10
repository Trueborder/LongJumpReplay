# Long Jump Replay — Project Knowledge

> Primary handoff document for human developers and Codex. Read this file before changing code.

## 1. Project identity

- **Project:** Long Jump Replay
- **Current source version:** 2.3
- **Primary platform:** Windows 11 x64
- **Language:** Python 3.12
- **GUI toolkit:** Tkinter / ttk
- **Video stack:** OpenCV, NumPy, Pillow
- **Physical controller:** Contour ShuttleXpress through HID, with keyboard fallback
- **Purpose:** Live replay assistance for long-jump take-off-board decisions
- **Current maturity:** Functional operator-assistance prototype; not a certified measuring or officiating system

The application shows live camera video while retaining a rolling buffer. An operator can freeze an attempt, inspect it frame by frame, preserve the attempt independently of the rolling buffer, optionally record a decision, and immediately return to live capture. It can also manage athletes and rounds, but competition management can be disabled for a clean judge-only interface.

### Staged native migration status

- The production/event path remains Python 3.12 with Tkinter and OpenCV.
- `native/` contains a compiled .NET 10 WPF migration preview split into Core, Windows Video, Infrastructure, App, and Tests.
- The native preview currently supports a deterministic synthetic source, continuous bounded capture during Replay, Freeze/Live, frame stepping, pause/resume, compatible JSON config reading, and bounded shutdown.
- `MediaFoundationCameraSource` provides friendly-name enumeration, CPU BGRA frame delivery, monotonic timestamps, real-time latest-frame acquisition, and bounded stop/disposal. The preview starts synthetically, lets the operator select a discovered camera, and falls back to synthetic after an open failure. Do not present it as event-ready until negotiated modes, reconnect, encoding, and physical-camera soak tests pass.
- `BUILD_NATIVE_PREVIEW.bat` publishes a self-contained Windows x64 preview folder under `release/`; this improves launch portability but does not promote the preview to the event-ready application.

## 2. Non-negotiable product rules

Preserve these rules unless the product owner explicitly changes them:

1. **Live capture must continue while replay is frozen.** Freeze affects playback, not capture.
2. **An unjudged attempt must not block the next athlete by default.** Returning Live completes the rotation slot as `Not decided` and advances once.
3. **Strict judging is optional.** `competition.require_decision_before_continue` enables it.
4. **Attempt media state, rotation completion, and decision are separate concepts.** Do not merge them again.
5. **The rolling live buffer must not be the only copy of a frozen attempt.** A frozen attempt is pinned, receives post-roll, and becomes a temporary cached video.
6. **The current/open attempt must not disappear during review.** Retention cleanup must protect selected/active media.
7. **The fixed timeline playhead stays visually stable.** The ruler/content moves below it.
8. **Timeline updates must reuse canvas items.** Do not delete and recreate all tick marks every frame.
9. **Expensive redraws are throttled or suspended while moving/resizing the window or interacting with menus.** Capture continues.
10. **Space must always control Freeze/Live even after clicking a button.** Focused widgets must not steal it.
11. **Evidence quality must not be silently reduced by performance presets.** Reduce preview/UI analysis work first. The separate Older PC mode is an explicit operator choice and may retain every second source frame; it must clearly disclose that tradeoff.
12. **The app must close even if a camera backend or worker misbehaves.** Shutdown has bounded waits and emergency release behavior.
13. **English and Czech are supported.** New user-facing strings must go through `src/i18n.py`.
14. **Dark mode controls must remain readable.** Always test combobox popups, selections, disabled text, and focus states.
15. **Competition management must be completely disableable.** Judge-only mode must remain simple.
16. **Take-off Assist may locate a candidate frame but must never decide Valid/Foul.** A human remains responsible.
17. **The athlete countdown is an operator aid only.** It must not create a result or be persisted in attempt metadata, evidence, or exports.
18. **A stalled camera must not leave post-roll open forever.** Finalize the available partial recording after a bounded monotonic deadline and retain a quality warning.
19. **System pause is a hard capture boundary.** It releases the camera, clears latest/live-buffer frames, blocks judging and timer starts, and creates no new attempt cache. Existing completed attempts are preserved.
20. **Window state and window geometry are distinct.** Remember maximized state separately; convert near-screen floating geometry to a real maximized window instead of opening an almost-borderless normal window.

## 3. Intended operator workflow

### Default optional-judging workflow

1. Camera runs and fills the rolling buffer.
2. Operator presses **Space**.
3. App creates an attempt at the current freeze timestamp and changes playback to replay.
4. Operator reviews with Left/Right or Shuttle jog wheel.
5. Operator may set `Valid`, `Foul`, or `Review`, but this is optional.
6. Operator presses **Space** again.
7. App returns to Live.
8. If the attempt has no verdict, it remains `Not decided`.
9. Its rotation slot is marked complete exactly once.
10. Competition session advances to the next athlete/round.
11. The next Freeze must work immediately.

### Strict workflow

When `competition.require_decision_before_continue` is true, Return Live may be blocked until a non-default decision is recorded. This mode is not the default.

## 4. Competition model

### Groups

- Internal group names: `Boys`, `Girls`
- Both can be enabled independently.
- Active group is stored in `competition.active_group`.

### Qualification order

For 8 athletes and 3 attempts:

```text
Round 1: 1, 2, 3, 4, 5, 6, 7, 8
Round 2: 1, 2, 3, 4, 5, 6, 7, 8
Round 3: 1, 2, 3, 4, 5, 6, 7, 8
```

The rotation is round-major, not athlete-major. Per-athlete attempt overrides are supported.

### Final round

- Optional.
- Default finalists: 8.
- Default extra attempts: 3.
- Finalists are selected manually because this application does not measure jump distance.
- Supported order modes: `same`, `reverse`, `manual`.

### Decision values

Defined in `src/models.py` as `AttemptDecision`:

- `Not decided`
- `Valid`
- `Foul`
- `Review`
- optional special results such as Passed / DNS / Withdrawn / Reattempt where enabled

Do not reuse `Pending` as a decision. `Pending` belongs to media/process state, not verdict.

### Competition board

Rows are athletes; columns are attempts. Soft colors are secondary cues; text/symbols remain primary for accessibility.

Every matrix cell is a single-click target. Clicking a cell containing a recording opens that exact attempt without changing the active rotation athlete; clicking an eligible empty cell selects that exact numbered attempt as the next recording target. The clicked cell owns the sole blue focus outline and uses a low-cost, smoothly interpolated light-accent pulse until navigation continues. Disabled cells retain the configured qualification/final-round rules. The exact-cell target is runtime-only, clears after the slot is filled or ordinary athlete navigation changes, and must not alter existing judging decisions or rotation completion. With automatic rotation enabled, a successful Freeze immediately projects the next round-major target (same attempt for the next athlete, wrapping from the final athlete to athlete 1 of the next attempt); returning Live commits the normal rotation to that same target.

- `✓` Valid
- `×` Foul
- `?` Review
- `●` completed, Not decided
- `–` Passed
- `DNS` Did not start
- `W` Withdrawn
- `↻` Reattempt

## 5. Runtime data flow

```text
Camera / synthetic / file source
        ↓
CaptureEngine capture thread
        ↓ latest raw frame
LatestFrameStore ───────────────→ Live preview
        ↓ encoder queue
JPEG encoder worker
        ↓ FramePacket(timestamp_ns, frame_index, jpeg_bytes)
TimeRingBuffer (rolling RAM buffer)
        ↓ Freeze
AttemptManager pins pre-roll + collects post-roll
        ↓
Temporary MP4 + JSON metadata in cache
        ↓
Replay / evidence PNG / exported MP4 / event package
```

### Timebase

- Internal sequencing uses monotonic nanosecond timestamps.
- Frame indexes are retained for frame stepping and evidence metadata.
- Export FPS is estimated from packet timestamps and normalized for common rates such as 120, 60, and 59.94.

## 6. Threading and shutdown

Tkinter must only be touched on the main GUI thread.

Background work includes:

- camera capture;
- JPEG encoding;
- attempt post-roll collection;
- temporary MP4 encoding;
- export copy/encoding;
- Take-off Assist analysis;
- Shuttle HID polling.

Communication back to the GUI uses queues and scheduled polling. Do not update widgets directly from workers.

`MainWindow.close()` coordinates shutdown. New workers must:

- have an explicit stop signal;
- avoid indefinite blocking;
- support a bounded `join`/shutdown timeout;
- not prevent process exit if the hardware driver is stuck;
- be covered by a close-during-work test.

## 7. Source map

### Entry point

- `app.py`
  - parses CLI arguments;
  - resolves portable config paths;
  - runs the GUI;
  - contains the headless synthetic self-test.

### Core modules

- `src/athlete_timer.py`
  - monotonic, testable athlete countdown controller;
  - READY, RUNNING, STOPPED, and EXPIRED lifecycle;
  - contains no Tkinter, attempt, judging, or persistence dependencies.

- `src/main_window.py`
  - main application composition and orchestration;
  - menu, toolbars, layouts, status, decisions, competition flow, clear-cache dialog, export, recovery, diagnostics, shutdown;
  - large file; prefer extracting focused components rather than adding more unrelated logic indefinitely.

- `src/config.py`
  - all config dataclasses;
  - validation;
  - migration from older config files;
  - performance presets;
  - atomic JSON save.

- `src/models.py`
  - immutable-ish packets and domain models;
  - attempt state, decision, markers, session metadata, timeline model.

- `src/capture.py`
  - `SyntheticSource`, `OpenCVCameraSource`, `VideoFileSource`;
  - `CaptureEngine` and latest-frame storage;
  - camera reconnect and encoding pipeline.

- `src/camera_devices.py`
  - enumerates friendly Windows Camera/Image PnP names without adding a runtime dependency;
  - maps displayed `index · name` labels back to the existing OpenCV `device_index`;
  - preserves a configured-index fallback when enumeration is unavailable or a device is missing.

- `src/ring_buffer.py`
  - thread-safe time-based JPEG packet ring buffer;
  - duration and memory limits;
  - timestamp lookup and snapshots.

- `src/attempts.py`
  - pinned attempt lifecycle;
  - pre-roll/post-roll;
  - temporary MP4 generation;
  - metadata and cache recovery;
  - selection, deletion, retention, export requests.

- `src/playback.py`
  - playback mode and frame/timestamp navigation.

- `src/exporter.py`
  - packet decoding;
  - FPS estimation/normalization;
  - MP4/AVI writer fallback;
  - PNG saving.

### UI modules

- `src/video_canvas.py`
  - video rendering, zoom/pan;
  - guide line and board ROI editing;
  - defers expensive render during window interaction.

- `src/timeline.py`
  - fixed-playhead professional timeline;
  - recycled canvas items;
  - coalesced updates;
  - overview/detail navigation and zoom.

- `src/competition_board.py`
  - athlete × attempt matrix.

- `src/settings_dialog.py`
  - 16-category modal settings window;
  - scrollable content with fixed Apply footer;
  - descriptions and performance-impact badges.

- `src/competition_wizard.py`
  - quick setup for a new competition or judge-only mode.

- `src/theme.py`
  - ttk style definitions and dark/light/system theme support.

- `src/i18n.py`
  - English/Czech translation dictionary and translator.

### Input and analysis

- `src/hotkeys.py`
  - application-wide key routing that outranks focused button behavior.

- `src/shuttle_hid.py`
  - Contour ShuttleXpress HID enumeration, packet parsing, poller;
  - keyboard fallback remains important for machines where the vendor driver owns HID access.

- `src/takeoff_assist.py`
  - ROI-local motion peak detection;
  - returns a candidate frame and confidence only.

### Portability

- `src/portable_paths.py`
  - source vs PyInstaller path handling;
  - writable data directory selection;
  - config provisioning and crash-log path.

## 8. Configuration structure

The default file is `config.json`. Important sections:

- `general`: language, confirmations, tooltips
- `camera`: source, device index, dimensions, requested FPS, FOURCC, backend, reconnect
- `buffer`: rolling duration, JPEG quality, encoder queue, RAM cap
- `attempts`: pre/post-roll, retention, max count/cache, temporary codec
- `athlete_timer`: integer countdown duration from 1 to 600 seconds (default 60)
- `competition`: groups, athlete counts, attempts, decisions, final round, optional features
- `display`: theme, layout, visible panels, guide, ROI, comparison
- `performance`: preset and GUI refresh controls
- `timeline`: detail range and frame snapping
- `takeoff_assist`: candidate analysis settings
- `export`: directories, codec, evidence options
- `hotkeys`: configurable action bindings
- `shuttle`: HID identifiers, action mapping, debounce

The current default camera requests:

```text
1280 × 720, 120 FPS, MJPG, DirectShow, device 0
```

Normal launches use the saved `camera` source, and new configurations default to Camera. The `--synthetic` CLI option is a transient test override: automatic config saves preserve the operator's saved source choice instead of replacing it with Synthetic.

A webcam may negotiate a lower real rate. Requested FPS is not proof of actual FPS; use capture diagnostics.

### Config compatibility

- Use dataclass defaults for new fields.
- Extend `_deep_update` migration behavior rather than breaking old JSON files.
- Validate every new setting in `AppConfig.validate()`.
- Save atomically through `save_config()`.
- Never make a missing new field crash a 2.2/2.3 user config.

## 9. UI layouts and controls

### Judge-station visual hierarchy

The main window is organized into stable task zones: application/camera/timer header, numbered-athlete context, video workspace, layered timeline, primary Freeze/Live and decision dock, and compact status reporting. Primary judging actions are visually stronger than layout, calibration, export, and maintenance controls. Both themes use the same hierarchy and semantic colors.

Settings uses four navigation groups (Essentials, Judging workflow, Replay workspace, Controls & system), active-page highlighting, page-introduction cards, card-based setting rows, visible impact badges, and a fixed Apply footer. The underlying sixteen pages remain separate to avoid presenting one very long form.

Every ordinary setting row follows the same three-column contract: Option (fixed width), Description (flexible), and Value (fixed width). Column headings are visible and localized. Every row has a useful localized description; `general.show_tooltips` immediately hides or restores the complete middle column, including its headings, without moving the Value column inconsistently. Checkboxes align to the same Value-column origin as entries, spinboxes, and selectors; individual label or description length must not move a control horizontally.

Checkboxes, comboboxes, combobox list popups, and classic Tk menus are themed as one component family. Checkbox indicator images are owned by `ThemeManager` for their full Tk lifetime. Dark/light theme application must also restyle existing File/View/Help and nested menus; native-looking defaults must not reappear after a runtime theme change.

All ttk button styles and combobox fields use compact, pill-like scalable image elements with transparent corners; the nine-slice image must not impose a larger minimum height than the control's own padding requires. Checkboxes use a circular accent indicator with a visible white check. On Windows, mapped classic menu windows and combobox popdowns request DWM rounded corners. Checkbox tests must verify both Tk selected state and different rendered checked/unchecked pixels so an invisible logical selection cannot regress unnoticed. The Settings category sidebar has its own always-visible scrollbar and mouse-wheel navigation, independent of the scrollable contents of each page.

The competition target strip belongs inside the Competition Board tab. It shows only the projected next athlete number and attempt plus special-result actions; the old Boys/Girls selector and Previous/Next buttons must not return. Every board cell is focusable. While the Competition Board tab is selected and visible, plain arrow keys move the persistent blue, softly pulsing focus regardless of which child widget owns focus; they never step replay frames in that context. Enter opens recorded content or selects an empty cell. Space always remains Freeze/Live. Modified arrows and all unrelated configured shortcuts keep their normal actions. Freeze keeps the board's active outline on the recorded athlete/attempt throughout judging; only a successful return to Live advances it to the next rotation cell. Right-clicking either a recorded or eligible blank cell exposes all decision variants. Choosing a status on a blank cell creates a metadata-only, zero-frame placeholder without changing the current athlete; Delete attempt content is enabled only when a record exists.

Supported layouts:

- `replay_pip`
- `side_by_side`
- `replay_only`
- `live_only`
- `comparison`
- `board_detail`

Core default hotkeys:

- Space: Freeze / Live
- Home: Return Live
- Left / Right: frame step
- Ctrl+PageUp / Ctrl+PageDown: previous / next attempt
- Alt+Left / Alt+Right: previous / next athlete
- N / V / F / U: Not decided / Valid / Foul / Review
- Ctrl+Delete: clear temporary recordings
- A / B / T / L: attempts / board / timeline / live preview
- F11: fullscreen
- G: guide
- C: comparison
- Ctrl+N: Competition Wizard
- Unassigned by default: Start / stop athlete timer (`timer_toggle`)

All bindings are configurable. Tests must cover that Space still works with a focused button.

### Athlete timer lifecycle

- READY displays the full configured duration and blinks only the READY text every 500 ms.
- READY starts only on an explicit timer click or configured timer hotkey while playback is Live.
- RUNNING uses monotonic elapsed time and rounds the visible remainder up to whole seconds. It is amber from 10 through 1 and red at expired `00:00`.
- RUNNING stops only on an explicit timer action or after a successful Freeze. A Freeze with no live frame leaves it running.
- STOPPED and EXPIRED restart from the full configured duration on the next valid timer action.
- A successful Replay-to-Live transition, a manual athlete change, or an applied duration change resets to READY without starting.
- The timer remains visible when competition management is disabled and never changes judging, capture, recording, rotation, or attempt metadata.

## 10. Timeline performance contract

Do not regress these properties:

- fixed central playhead;
- content scrolls beneath it;
- canvas objects are created once and reused;
- requests are coalesced with idle/scheduled updates;
- update rate is limited by the performance profile;
- the visible timeline can raise the main UI scheduler above preview FPS so its cursor is not accidentally capped by a slower preview setting;
- hidden or suspended timeline does no expensive work;
- dragging and overview seeking remain responsive;
- window move/resize suspends expensive rendering and resumes with the latest frame.
- the taller layered ruler retains a fixed shaded focus band, strong centre playhead, distinct Freeze marker, availability band, and full-media overview without creating canvas items during updates;
- interaction guidance is a dedicated layout row below the canvas, so it cannot be clipped by the ruler height or paned-window sash.

When changing timeline code, run both logic and GUI tests plus `tools/benchmark_timeline.py`.

## 11. Performance philosophy

### Runtime observability

- Source and portable runs write a rotating `LongJumpReplay-runtime.jsonl` beside the active config: 2 MB per file with three backups.
- Logs cover application/camera lifecycle, reconnect errors, Freeze success/failure, Live return, decision changes, system pause/resume, shutdown duration, unhandled worker exceptions, and fatal startup failures.
- Help > Diagnostics reports bounded UI tick average, p95, maximum, stalls at or above 100 ms, and uptime alongside capture/buffer statistics.
- Runtime diagnostics are operational data only and must never be copied into attempt metadata, evidence, or exports.
- `tools/soak_diagnostics.py` and `RUN_STABILITY_CHECK.bat` provide a repeatable synthetic capture report. Passing requires at least 90% of requested synthetic FPS, zero queue drops, zero encoder failures, and no remaining capture workers.

The PC fan/noise is a real product concern. Performance presets are:

- `quiet`
- `balanced` (default)
- `high`
- `evidence`
- `custom`

Settings with performance consequences display Low / Medium / High / Very high impact labels.

The explicit Older PC mode is stronger than the ordinary Quiet presentation preset. It applies Quiet UI rendering, a 15-second/1 GB live buffer, JPEG quality 72, a 64-frame encoder queue, 128-pixel assist analysis, and `store_every_nth_frame = 2`. Camera capture remains at the configured FPS, so a 120 FPS source yields a 60 FPS retained replay. It is available only through Settings.

Optimization order:

1. reduce preview refresh rate;
2. reduce timeline/status/list refresh rate;
3. lower preview render scale;
4. pause hidden panels;
5. reduce work while minimized;
6. throttle Take-off Assist analysis resolution;
7. preserve original buffered/evidence quality unless the operator explicitly changes it.

Do not tie UI preview FPS to capture FPS. A 120 FPS recording can have a 30–60 FPS preview.

## 12. Storage and portable behavior

Relative paths normally include:

- `cache/` — temporary attempts and metadata
- `exports/` — manually exported videos
- `evidence/` — raw/annotated evidence images and sidecar metadata
- logs/config in the writable application data directory when the EXE folder is not writable

`Clear temporary recordings` must not delete exported MP4 or evidence files.

The portable folder build is preferred over one-file:

- faster startup;
- easier diagnostics;
- fewer antivirus false positives;
- more predictable codec/DLL behavior.

## 13. Tests and verification

### Standard Windows development commands

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest
python app.py --self-test
python app.py --synthetic --windowed
```

### Important regression scenarios

Always test changes affecting workflow against:

1. Freeze → review → Live without verdict → next athlete → Freeze again.
2. Strict decision mode still blocks when enabled.
3. Athlete rotation after all athletes completes the next round.
4. Final round uses selected finalists and configured order.
5. Space works after clicking any button.
6. Attempt remains accessible beyond live-buffer expiry.
7. Clear live buffer does not stop capture.
8. Clear unresolved does not delete exports/evidence.
9. Close from Live.
10. Close during post-roll.
11. Close during MP4 encoding/export.
12. Timeline item count does not grow during updates.
13. Dark/light combobox popup text remains readable.
14. Apply footer is visible on every Settings page.
15. Menu interaction does not rebuild the menu or freeze capture.
16. Timer click and configured hotkey share the same action, and starts outside Live are rejected.
17. Successful/failed Freeze, Replay-to-Live, manual athlete change, and runtime duration application preserve the timer lifecycle above.
18. Timer READY blinking, warning/expired colors, translations, and far-right header layout remain correct in light and dark themes.
19. A stalled post-roll finalizes partial media with a warning instead of remaining Collecting.
20. Strict-mode deletion enters a consistent Live state without completing the deleted rotation slot.
21. Clear-recording Live transitions reset runtime-only review aids through the centralized Live path.
22. Dangerous capture sampling, display, analysis, export, duplicate-hotkey, file-source, and device values are rejected during config validation.
23. English and Czech translation dictionaries expose the same keys.
24. Older PC mode preserves configured camera FPS, applies bounded low-resource values, validates successfully, and is loadable from Settings.
25. Main-screen pause stops and resumes capture, clears the live buffer/latest frame, blocks Freeze and timer actions, and leaves existing attempts intact.
26. Near-screen saved geometry opens maximized while ordinary reduced geometry stays restored.
27. Camera Settings enumerates friendly names, keeps a read-only `index · name` selector, and writes the selected numeric OpenCV index back to configuration.
28. When the Competition Board tab is selected, plain arrows navigate cells from every child focus target and never step frames; Enter activates the cell, while Space still controls Freeze/Live. Recordings restores normal frame stepping immediately.
29. Status text and timeline guidance retain full layout rows at reduced window heights, and the visible timeline scheduler reaches the selected refresh target.
30. Every Settings row has a localized description; the Show setting descriptions checkbox hides and restores the Description column immediately.
31. Freeze keeps the active board cell on the attempt being judged, and return to Live advances it exactly once.
32. Eligible blank board cells accept right-click decisions as zero-frame placeholders; repeated edits update the same record and deletion stays disabled until content exists.

### Headless note

Tkinter GUI tests require a display. On Windows, run them normally in an interactive desktop session. On Linux CI, use `xvfb-run -a python -m pytest`.

### Current handoff verification

At the time this handoff was prepared, the Windows source suite passed **67 tests**, the synthetic pipeline self-test completed attempt MP4/export with no remaining workers, and the short 120 FPS diagnostic soak retained 600/600 frames with zero drops or failures. The .NET 10 Release solution built with zero warnings, all six native lifecycle/retention/config tests passed, and the self-contained published preview remained alive through its bounded startup/camera-enumeration smoke before closing. This does not replace visual GUI inspection, a four-hour soak, physical webcam/120 FPS camera, full native feature parity, and actual ShuttleXpress testing.

## 14. Build and release

### Source setup

- `INSTALL_WINDOWS.bat`

### Run

- `RUN_SYNTHETIC.bat`
- `RUN_CAMERA.bat`
- `SELF_TEST.bat`

### Portable release

- `BUILD_PORTABLE.bat`
- output: `release\LongJumpReplay-2.3-Windows-x64.zip`

### Single EXE

- `BUILD_SINGLE_EXE.bat`
- supported, but not the recommended distribution format.

### GitHub Actions

- `.github/workflows/build-windows-exe.yml`
- runs tests, source self-test, PyInstaller build, frozen self-test, artifact ZIP.

Before a release:

1. run all tests;
2. run source self-test;
3. test synthetic GUI manually;
4. test actual camera and actual FPS;
5. test Shuttle jog/ring/buttons;
6. build portable release;
7. run frozen self-test;
8. extract release ZIP into a clean folder and launch it;
9. verify config, cache, export, evidence, and crash-log paths;
10. update version in README, build scripts, PyInstaller metadata, workflow, changelog, and filenames consistently.

## 15. Known limitations and unverified areas

- Not certified by World Athletics or a national federation.
- Does not measure jump distance.
- Finalists are selected manually unless future distance entry/import is added.
- OpenCV camera property requests may be ignored by drivers.
- Real 120 FPS depends on camera mode, exposure, USB bandwidth, driver, codec, and computer.
- Direct Shuttle HID may be unavailable when the Contour driver claims the device; keyboard profile fallback is intentional.
- Synchronization of multiple cameras is not implemented and is currently out of scope.
- Automatic Valid/Foul classification is intentionally not implemented.
- Windows EXE must be built and tested on Windows; PyInstaller is not a cross-compiler.
- Some hardware/codec failures can only be reproduced on the target machine.

## 16. Coding conventions

- Python 3.12 compatible syntax.
- Use type hints for new public functions and nontrivial data structures.
- Prefer dataclasses for configuration/domain data.
- Keep GUI calls on the main thread.
- Use queues/events for worker communication.
- Use `time.monotonic_ns()` for runtime sequencing.
- Avoid unbounded queues and unbounded joins.
- Do not perform disk I/O, camera probing, or video encoding inside GUI callbacks.
- Keep user-visible strings out of widgets and in `src/i18n.py`.
- Add a short description and performance-impact level for every new setting that can affect CPU/GPU/RAM/disk/UI responsiveness.
- Preserve backward config compatibility.
- Add tests before or alongside fixes.
- Never claim a Windows/hardware path was tested unless it actually was.

## 17. How Codex should work in this repository

Before editing:

1. Read `AGENTS.md`, this file, and the relevant source/test files.
2. Run `git status` and do not overwrite unrelated user changes.
3. Run the smallest relevant test first.
4. Explain the root cause before large refactors.
5. Prefer focused changes over rewriting working subsystems.

After editing:

1. Run affected unit tests.
2. Run the full test suite.
3. Run `python app.py --self-test` for pipeline-affecting changes.
4. Manually run `python app.py --synthetic --windowed` for GUI changes.
5. Update this knowledge file for every project change. Add a concise note describing what changed and update the relevant existing section when architecture, workflow, guarantees, testing, setup, or known limitations are affected.
6. Update `CHANGELOG_*.md` for user-visible changes.

Do not:

- remove optional-judging behavior;
- reintroduce live-buffer expiry for selected attempts;
- make Take-off Assist authoritative;
- update Tk widgets from worker threads;
- lower evidence quality through a preset without explicit user intent;
- silently delete exported or evidence files;
- block shutdown indefinitely;
- add untranslated strings;
- rebuild menus/timeline canvas objects every frame.

## 18. Suggested next engineering work

The prepared implementation sequence is maintained in `docs/IMPLEMENTATION_ROADMAP.md`. It intentionally keeps athlete names, clubs, distances, and broader meet management out of scope.

Highest-value future work, in rough order:

1. Break `src/main_window.py` into focused controllers without changing behavior.
2. Add an in-app camera capability scanner that enumerates actual supported resolution/FPS combinations rather than only testing requested values.
3. Add richer event/session persistence and crash-recovery tests on Windows.
4. Improve numbered attempt-rotation presets without adding athlete identity or distance management.
5. Profile CPU usage on weak and strong Windows laptops and tune presets from real measurements.
6. Add Windows-native UI automation smoke tests for menus, dark combobox popups, window move/resize, and shutdown.
7. Validate the physical 120 FPS camera and ShuttleXpress before any official event usage.

## 19. Recent UI workflow changes

- Settings and Competition Board scrolling now handle Windows and Linux wheel/button events consistently, refresh scroll regions after content changes, and use themed scrollbar states. Settings Hotkeys puts Defaults above the table; double-click changes a row and the right-click menu restores one default with duplicate protection. A first-run guided tutorial is persisted in `general.onboarding_completed` and can be reopened from General settings. Applying camera/live-buffer changes asks whether to restart immediately; the relaunch preserves the script or frozen executable arguments. Board guide width is passed to all video canvases and evidence overlays instead of using a fixed preview width.

- Judge controls are grouped into frame review and judging categories. Frame, verdict, and Board setup buttons use equal widths and square native ttk rendering; Board setup stays on the right edge.
- Verdict controls are greyed whenever there is no active frozen attempt to judge (including Live and system-paused states).
- Competition-board scrolling handles Windows and Linux wheel events, including horizontal Shift-wheel scrolling, while preserving keyboard cell navigation.
- Export, cache clearing, and camera pause expose an indeterminate progress bar in the status bar while work is active.
- Camera startup and resume use the same bounded status progress feedback. When no live frame arrives, the video workspace offers a themed Help button with source/index, permissions, competing-app, capture-mode, and diagnostic guidance. A branded splash screen keeps startup state visible while the judge station is prepared.
- The splash uses the original `assets/long_jump_splash.png` hero image unchanged, with a high-contrast LONG JUMP / REPLAY header, startup badge, progress bar, and small `© 2026 · Developed by Tomáš Pisár` credit. PyInstaller build entry points include the image asset.
- `py app.py --splash-preview` opens that splash by itself for visual review and exits when the user presses Escape; it does not start camera, shuttle, buffer, or attempt workers.
- Normal startup runs a randomized 0.5–2.0 second preparation sequence from 0% to 80%, updates a themed action-status strip beneath the bar, initializes the application at 80%, then advances to 100% and removes the splash as the main window becomes ready.
- Splash presentation uses a centered fixed geometry and appears/disappears immediately; there is no startup resize animation.
- The main control dock has one larger Freeze/Live toggle. Frame review and judging buttons are enabled only for a frozen attempt and use the same disabled/faded treatment; Not decided uses a neutral pending style rather than black. Board Setup is a matching labeled group, and the system pause button/mode badge share a fixed width.
- The athlete countdown duration is managed in a dedicated Athlete timer settings category with a Low performance-impact badge.
- On the Competition Board, Up/Down may move between athlete rows; Left/Right are reserved for replay frame stepping after Freeze and never change the selected attempt column.
- Export, Delete, and Clear all temporary recordings share one equal-width muted action row. Board calibration position/size fields are intentionally absent from Settings and are changed by dragging directly on the main video. All application-owned dialogs use the current ThemeManager palette.

## 20. Build entry points

- `CREATE_SINGLE_EXE.bat` is the one-click Python/PyInstaller build entry point. It prefers the project virtual environment, falls back to Python 3.12 discovery, runs the source and frozen self-tests, creates `release\LongJumpReplay-2.3.exe`, and writes its SHA-256 sidecar.

## 21. Definition of done for changes

A change is done only when:

- the requested behavior works;
- existing core workflows remain intact;
- tests cover the regression where practical;
- full tests pass;
- GUI changes are manually inspected in light and dark modes;
- performance-sensitive changes are profiled or at least benchmarked;
- shutdown still leaves no workers;
- documentation/config migration is updated;
- `PROJECT.KNOWLEDGE.md` records the change;
- claims clearly distinguish simulated tests from real Windows/hardware tests.

## 22. UI consistency update (2026-08-10)

- The recordings footer keeps Export, Delete, and Clear all temporary recordings in one equal-width, muted action row beside the recordings list.
- Settings no longer edits guide/ROI positions or dimensions numerically. Those values remain owned by the visual Board calibration interaction in the main video; Settings keeps visibility and line-width controls plus plain-language guidance.
- Performance profiles now have an explicit selection flow and explain that normal profiles change presentation/analysis workload without changing camera capture or evidence quality. Older PC mode remains the explicit frame-dropping trade-off.
- Application-owned message and confirmation dialogs use shared themed ttk content, including dark-mode confirmations and diagnostics. Startup splash presentation is instantaneous on entry and exit.
- Hotkey Settings places Defaults above the table; row editing is by double-click and per-row reset is available from the themed context menu.
- Recordings-tab actions are state-aware: Export/Delete are muted and disabled without a selected capture; Clear all temporary recordings is red only when temporary attempts exist. Clearing all resets the competition board focus and current target to athlete 1, attempt 1.
- Export/Delete now follow the explicit capture selected in either Recordings or Competition Board. Clicking an empty board cell clears that action target immediately, so an older replay cannot be exported or deleted accidentally.
- Settings explanatory content is responsive: the plain-language glossary uses two columns of term cards, while hero, row, performance, and calibration descriptions wrap to their actual available width. Settings section columns now expand evenly so help text and controls remain inside the scrolled page at its minimum size.
- Settings Value-column selectors use a bounded request width and a flexible grid column, so long camera, layout, and ShuttleXpress option lists do not push controls beyond the page edge.
- Settings Value fields now use a compact fixed lane with smaller default Entry/Spinbox/Combobox requests. Settings and Competition Wizard dropdowns retain the themed colours but use normal rectangular native list and field rendering.
- Camera startup now presents a translated “Looking for input from all sources” overlay with a 10-second progress bar. A background probe checks camera indices 0 and 1 without blocking Tk; if no frame arrives, the progress overlay is replaced by Try again and Help with camera actions. Retry stops and restarts capture asynchronously, starts its fresh 10-second window only after restart, cancels stale probes, and still shows recovery actions even when an earlier capture attempt had already incremented the lifetime frame counter.
