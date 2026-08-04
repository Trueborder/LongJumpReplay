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

Every ordinary setting row follows the same three-column contract: Option (fixed width), Description (flexible), and Value (fixed width). Column headings are visible and localized. Checkboxes align to the same Value-column origin as entries, spinboxes, and selectors; individual label or description length must not move a control horizontally.

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
- hidden or suspended timeline does no expensive work;
- dragging and overview seeking remain responsive;
- window move/resize suspends expensive rendering and resumes with the latest frame.
- the taller layered ruler retains a fixed shaded focus band, strong centre playhead, distinct Freeze marker, availability band, full-media overview, and an interaction hint without creating canvas items during updates.

When changing timeline code, run both logic and GUI tests plus `tools/benchmark_timeline.py`.

## 11. Performance philosophy

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

### Headless note

Tkinter GUI tests require a display. On Windows, run them normally in an interactive desktop session. On Linux CI, use `xvfb-run -a python -m pytest`.

### Current handoff verification

At the time this handoff was prepared, the source test suite passed **43 tests** under a virtual display. This does not replace testing on the target Windows machine, physical webcam, target 120 FPS camera, and actual ShuttleXpress.

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

## 19. Definition of done for changes

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
