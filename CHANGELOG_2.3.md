# Long Jump Replay 2.3 — Changelog

## Settings column alignment

- Standardized setting rows into fixed Option, Description, and Value columns.
- Labels, impact badges, help text, checkboxes, entries, spinboxes, and selectors now align vertically across each Settings page.
- Added visible localized column headings and a wider minimum Settings workspace to prevent controls from drifting or wrapping into inconsistent positions.

## Camera and judging pause

- Added a prominent Pause system / Resume system switch to the main header.
- Pause asynchronously releases the camera, drains capture work, clears the live RAM buffer, resets the timer, and blocks new judging actions without deleting completed attempts.
- Resume reconnects the configured source and begins a fresh live buffer.
- Near-screen floating geometry is normalized to a genuinely maximized window; maximized versus restored state is remembered separately from normal geometry.

## Low-resource operation

- Added an explicit Older PC mode in Settings.
- The mode reduces preview/timeline refresh, assist analysis size, JPEG work, encoder queue pressure, live-buffer duration, and RAM use while leaving the configured camera capture rate unchanged.
- A 120 FPS source retains 60 FPS in low-resource mode by intentionally storing every second frame; this quality tradeoff is operator-selected rather than silently applied by normal performance presets.
- Adaptive preview throttling now drops to 12 Hz when the encoder is falling behind.

## Judge-station interface remake

- Reworked the main screen into clearer header, competition context, video, timeline, decision, and status zones.
- Enlarged the primary Freeze/Live and judging actions while reducing visual competition from secondary controls.
- Rebuilt Settings with task-based navigation groups, card-style fields, stronger page introductions, active-page highlighting, and a larger workspace.
- Rebuilt the timeline with a taller layered ruler, fixed focus band, clearer availability and Freeze markers, a stronger playhead, and visible interaction guidance.
- Updated both light and dark palettes for improved contrast and visual hierarchy.

## Reliability hardening

- Attempts now finalize available frames with a warning after a bounded post-roll capture stall instead of remaining in Collecting indefinitely.
- Replay-to-Live state handling is centralized so deletion and clear-recording workflows remain consistent with timer and playback state.
- Deleting an undecided attempt in strict mode no longer leaves playback pointing at deleted media.
- Added validation for capture sampling, display dimensions, Take-off Assist, export FPS, hotkey collisions, file sources, and Shuttle timing/identifiers.
- Attempt recovery metadata is now written atomically.

## Athlete attempt timer

- Added a clickable countdown at the far top-right of the header, available in competition and judge-only modes.
- Defaults to 60 seconds and supports a 1-600 second duration in Attempts & decisions settings.
- Added an unassigned configurable hotkey using the existing collision checks.
- READY blinks; the final ten seconds are amber; expiry is red and has no sound or automatic result.
- Successful Freeze stops a running timer, while failed Freeze does not; Replay-to-Live, manual athlete changes, and applied duration changes reset it.
- Timer state remains runtime-only and is excluded from attempts, evidence, and exports.

## Attempt workflow

- A frozen recording no longer requires a verdict before the operator can continue.
- New attempts start as **Not decided**.
- Returning to Live completes the current roster slot and advances to the next athlete when automatic advancement is enabled.
- Optional strict mode still requires Valid, Foul, or Review before returning to Live.
- Recording state, roster completion, and judging are stored separately.

## Competition management

- Correct round order: every athlete completes attempt 1 before attempt 2 begins.
- Default three qualification attempts.
- Optional final round with Top 8, Top 10, Top 12, or a custom number and three additional attempts by default.
- Finalists are selected manually because this application does not measure jump distance.
- New scrollable athlete-by-attempt competition board with soft status colours and symbols.
- Optional Passed, DNS, Withdrawn, and Reattempt results.
- Competition management can be disabled completely for a clean judge-only replay screen.
- Optional next-athlete overlay, state banner, crash recovery, competition export, keyboard controls, operator mode, and camera diagnostics.

## Start Competition Wizard

- New button on the main screen and File menu.
- Configures judge-only/competition mode, language, athletes, attempts, final round, camera, performance, replay retention, and storage.
- Can clear old temporary recordings before a new event.

## Settings remake

- Sixteen navigable categories in a scrollable modal window.
- Fixed bottom action bar: Restore Defaults, Cancel, Apply, Apply & Close.
- English and Czech interface.
- Descriptions for camera indices and most non-obvious settings.
- Explicit performance-impact labels: Low, Medium, High, Very high.
- Performance presets: Quiet, Balanced, High performance, Evidence, and Custom.
- Dark-theme entries, spinboxes, comboboxes, dropdown lists, disabled states, and selections restyled for readable contrast.

## Performance and menu responsiveness

- File/View/Help moved to lightweight, static popup menus in the application header.
- Menus are never rebuilt by the camera/video update loop.
- Optional menu throttle temporarily reduces expensive preview redraws while a menu is open.
- Hidden panels, minimized windows, preview scale, timeline refresh, and adaptive load reduction are configurable.
- Performance presets reduce display and analysis work without silently lowering the configured live-buffer evidence quality.

## Recording management

- Clear Temporary Recordings dialog reports recording count, unresolved count, cache size, and live-buffer length.
- Options: clear everything, clear only the live buffer, or clear unresolved recordings.
- Exported MP4 files and evidence images remain untouched.
- Competition package export creates a ZIP with CSV, JSON configuration, temporary recordings, metadata, and evidence files.
