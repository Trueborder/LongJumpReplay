# Long Jump Replay implementation roadmap

This roadmap is governed by `PRODUCT_STRATEGY.md`: the product focuses on defensible take-off-board video adjudication rather than replacing AK2. Lightweight names, bibs, clubs, categories, attempt context, and optional whole-centimetre distance/wind metadata are in scope when they improve the judge workflow; broader meet management remains out of scope.

## Phase 1 — judge-station interface and reliability

- Group Settings by operator task with a card-based layout, active navigation, clearer descriptions, and a fixed action footer.
- Give the judge screen distinct context, video, timeline, decision, and system-status zones.
- Rebuild the timeline as a layered ruler with a fixed focus band, stronger Freeze/playhead hierarchy, full-media overview, and visible interaction guidance.
- Finalize partial post-roll after a bounded capture stall instead of leaving an attempt stuck in Collecting.
- Centralize Replay-to-Live transitions so deletion, clearing, rotation, and timer state remain consistent.
- Reject configuration values that can break capture, replay, comparison, export, hotkeys, or device polling.
- Write attempt recovery metadata atomically.

## Phase 2 — background task center

Introduce a focused `BackgroundTaskController` owned by the main window.

- Move competition ZIP creation, evidence PNG writing, and manual frame saving off the Tk thread.
- Report queued/running/completed/failed state through the existing event queue.
- Show progress and destination in a compact task drawer rather than modal dialogs.
- Allow retry for failed exports and cancellation before a task starts writing its final file.
- Use temporary output names and atomic final replacement so interrupted exports are never mistaken for complete files.
- Add bounded shutdown tests for active evidence and competition exports.

## Phase 3 — camera readiness

- Enumerate practical camera backend, resolution, codec, and FPS combinations.
- Measure each candidate rather than trusting requested properties.
- Add a pre-event readiness screen for measured FPS, encoder headroom, dropped frames, RAM-buffer duration, free disk space, export writability, and Shuttle status.
- Save the last known-good camera profile without silently lowering evidence quality.
- Produce a copyable diagnostic report for troubleshooting.

## Phase 4 — recovery and auditability

- Detect corrupt session metadata and orphaned temporary video instead of silently skipping it.
- Offer repair, keep, or discard actions with explicit file counts and sizes.
- Add a compact event audit log for Freeze, Live, decision changes, deletions, exports, warnings, and recovery operations.
- Keep the audit log separate from evidence and make it clear that the application is an operator-assistance tool, not a certified measurement system.

## Phase 5 — maintainability and release confidence

- Extract judge workflow, export, diagnostics, competition rotation, and view orchestration from `main_window.py`.
- Convert Settings definitions to declarative field metadata so layout, validation, search, impact labels, and translations share one source.
- Move remaining user-visible literals into `src/i18n.py` and add a translation-key parity test.
- Add pull-request CI, coverage reporting, corrupt-cache fixtures, stalled-camera tests, export-failure tests, and Windows UI smoke tests.
- Keep physical camera, ShuttleXpress, and packaged EXE verification as explicit release gates.

## Phase 6 â€” staged Windows-native migration

The initial .NET 10 WPF vertical slice is present under `native/`: separated projects, compatible config reading, a deterministic synthetic source, bounded continuous capture, Live/Freeze/Replay, stepping, pause/resume, shutdown, and executable tests.

Cutover remains gated in this order:

1. Add explicit Media Foundation mode negotiation and reconnect to the selectable source, then pass a physical-camera friendly-name/open/soak test.
2. Add low-copy pre/post-roll retention plus temporary MP4 encoding while preserving partial-attempt recovery and evidence quality.
3. Port attempt persistence/recovery and compare Python/native outputs from the same synthetic packet fixtures.
4. Port the numbered competition board, optional judging, timer, settings, English/Czech localization, exports, evidence, and HID input.
5. Pass four-hour soak, repeated start/stop, low-disk, forced-failure, DPI/theme/input, physical camera, and packaged self-contained Windows tests before changing the default launcher.

Do not remove or weaken the Python implementation during these gates.
