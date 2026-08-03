# Long Jump Replay implementation roadmap

This roadmap keeps the product focused on one job: helping a judge review take-off-board fouls. Athlete identity remains number-based; names, clubs, distances, and broader meet-management features are intentionally out of scope.

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
