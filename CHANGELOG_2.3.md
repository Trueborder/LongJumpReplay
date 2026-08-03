# Long Jump Replay 2.3 — Changelog

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
