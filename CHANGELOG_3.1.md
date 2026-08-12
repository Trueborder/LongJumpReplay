# Long Jump Replay 3.1 — Changelog

## Reliability and performance audit (2026-08-11)

- Malformed or structurally invalid settings are quarantined as a numbered `.corrupt` backup and replaced with validated defaults, so a damaged configuration no longer prevents startup.
- Temporary attempts that are still collecting, encoding, or exporting can no longer be deleted out from under their worker; exported video and metadata are installed through temporary files.
- Replay decoding keeps a small bounded recent-frame cache and avoids repeated seeks during sequential review, reducing OpenCV seek overhead on the GUI thread.
- Video preview canvases reuse their image, overlay, guide, and ROI items instead of deleting and recreating the entire Tk canvas graph for every frame.
- Evidence files now come from the selected attempt frame and are written atomically; partial evidence artifacts are cleaned up after a failed write.
- Fixed the native preview retention path so a frozen frame cannot make its capture buffer grow without bound.

## Windows packaging repair

- Replaced the Python/PyInstaller setup wrapper with a native PowerShell deployment script embedded in an IExpress self-extracting installer. `BUILD_INSTALLER.bat` rebuilds the current portable payload, embeds a matching version manifest, validates the payload before installation, safely replaces the Program Files application directory, and creates an all-users desktop shortcut.
- Added `BUILD_CUSTOMER_RELEASE.bat` as the single customer-release entry point. It validates source and frozen builds, replaces the existing `release` folder, creates the administrator-elevated installer and checksums, stages customer documentation, and builds the deployable website with the same installer while excluding owner-only licensing material.
- Build scripts now detect and preserve stale virtual environments before creating a fresh Python 3.12 environment.
- Single-file PyInstaller builds disable UPX compression to reduce Windows bootloader and antivirus extraction failures.
- Corrected the portable PyInstaller spec to produce the one-folder executable expected by the portable build and frozen self-test.
- Isolated generated single-file specs so they cannot overwrite the portable spec.
- Fixed the frozen EXE first-run license dialog so it is visible and focused instead of leaving a hidden process waiting for activation.
- The portable one-folder build remains the recommended production distribution.
- Added the owner/support license-generator GUI with clipboard and file-save actions, plus an admin workflow document. The private signing key remains external to the customer build.

## Customer release cleanup

- Removed developer-only Diagnostics, operator/setup mode, synthetic test source, advanced troubleshooting settings, and cache-folder shortcuts from the normal customer interface.
- Kept synthetic capture, self-tests, recovery compatibility, and diagnostic implementation available for development and support without exposing them in the customer workflow.
- Removed the developer credit from the startup splash and stopped copying synthetic/self-test launchers into the customer ZIP.
- Camera startup feedback now keeps the initial all-sources message, then identifies the selected camera after a settings-triggered restart.
- During the initial all-sources check, the first working camera is now selected for the main live video; an unavailable camera 0 can automatically fall back to camera 1.

## Sales website

- Reworked the static sales site around the actual Capture, Freeze, Replay, and Decide workflow, with a clearer runway-control visual system and focused installer messaging.
- Corrected broken English symbols, Czech diacritics, the `Kč` price, and misleading MSI wording in both source and deployable copy.
- Fixed the static build to read rewritten HTML and CSS explicitly as UTF-8, preventing the build step from reintroducing mojibake.
- Tightened the responsive hero, navigation, facts, screenshots, offer, and download layouts; verified the page at 1440 px desktop and an emulated 390 px mobile viewport without horizontal overflow.
- Added a branded `TP` browser-tab icon across the static site and expanded the bilingual About page into four numbered sections covering approach, focus, process, and current work.
- Replaced the LongJumpReplay product gallery and its non-JavaScript fallbacks with the current main-station, recordings, and competition-board screenshots from the project screenshot set.
- Redesigned `tomaspisar.cz` as a responsive Evidence Desk: a clearer product hierarchy, sports-specific Barlow typography, timing and take-off-line details, calmer flat panels, current-page navigation, SVG controls, improved mobile menu state, and a keyboard-friendly screenshot dialog in both dark and light themes.

## Usability and operator guidance

- Fixed the large CPU spike after zooming video. Preview rendering now crops to the visible source region before scaling, keeping temporary image work bounded by the viewport even at 10× zoom.
- Main-window startup now restores every View-menu workspace element. Showing the timeline also restores a usable 220 px pane instead of leaving it collapsed along the bottom edge.
- Reworked the Competition Wizard into a fast adaptive event setup. It opens directly at format selection, validates group/final dependencies, previews board capacity, reports station readiness, protects existing recordings with an explicit Keep/Clear choice, and keeps camera/performance/storage editing in Settings.
- Fixed cross-platform scrolling in Settings and the Competition Board, including themed scrollbar hover/pressed states.
- Added right-click editing for every listed application hotkey, with duplicate-binding protection and restore-default actions.
- Added a plain-language Settings glossary for Buffer, ROI, FPS, Codec, HID, and JPEG quality.
- Added a persisted first-run guided tutorial with a Settings action to show it again.
- Added a restart confirmation after applying camera/live-buffer changes; the relaunch preserves script or frozen-executable arguments. Wired the board guide-line width through preview, calibration, and evidence rendering.
- Added a camera Help button when no live frame is available, with plain-language checks for source type, camera index, permissions, competing apps, capture mode, and diagnostics.
- Added a branded startup preparation window and bounded indeterminate progress feedback while starting/resuming/stopping the camera system.
- Refined the startup splash with the original long-jump hero photograph, stronger two-tone product header, startup state badge, and the restored `© 2026 · Developed by Tomáš Pisár` footer credit.
- Added `--splash-preview` so the splash can be inspected without starting the camera or judge station.
- Replaced the indeterminate splash bar with a themed 0–100% startup sequence, staged at 80% while the application initializes, and added a live action-status strip beneath it.
- Added a visible centered geometry reveal and contraction to the startup splash and its standalone preview, avoiding unreliable platform alpha transitions.
- Unified Freeze and Live into one larger primary toggle; frame stepping now enables only for a frozen attempt, disabled controls share the faded theme treatment, and Board Setup has its own matching control group. The system pause button and mode badge now use the same width.

## Judge controls and timer settings

- Replaced rounded button artwork with compact square ttk controls and grouped frame-review/verdict actions at equal widths; Board setup remains on the right.
- Verdict controls now grey out when no frozen attempt is being judged.
- Improved Competition Board wheel scrolling and added status-bar progress feedback for exports, clearing, and camera pause.
- Moved athlete-timer duration into its own translated settings category.

## Reliability telemetry and staged native migration

- Added bounded JSON-lines runtime logging for application lifecycle, camera recovery, Freeze/Live, decision changes, system pause, shutdown timing, worker failures, and fatal startup failures.
- Added UI tick average, p95, maximum, stall count, and uptime to Diagnostics without placing telemetry in attempts, evidence, or exports.
- Added a repeatable synthetic soak command with machine-readable FPS, queue, failure, buffer, and worker acceptance results.
- Added a compiled .NET 10 WPF migration preview with isolated Core, Windows Video, Infrastructure, App, and Tests projects.
- Implemented the native synthetic Live/Freeze/Replay vertical slice, continuous capture during review, bounded buffer retention, frame stepping, camera pause/resume, existing-config reading, and bounded shutdown.
- Added selectable Windows Media Foundation capture with friendly-name device enumeration, CPU BGRA delivery, monotonic timestamps, real-time latest-frame acquisition, bounded release, and synthetic fallback after an open failure; physical hardware validation remains gated.
- Added a self-contained Windows x64 native-preview build command so the preview output does not require a separately installed .NET runtime.
- Kept physical camera/event operation on the verified Python application until Media Foundation capture and full workflow parity pass the documented gates.

## Camera source startup

- Kept Camera as the normal-launch and new-configuration default, and made the `--synthetic` test flag transient so it cannot overwrite the saved source selection.

## Competition board interaction

- Made every attempt cell respond to a single click: recorded cells open their exact replay, while eligible empty cells become the exact next recording target.
- Added a persistent blue outline and smooth light-accent pulse to the clicked cell.
- Corrected the post-Freeze board projection to advance across athletes within the same attempt before wrapping to athlete 1 of the next attempt.
- Made plain arrows consistently navigate cells whenever the Competition Board tab is selected, regardless of focused child widget; Recordings restores frame stepping immediately.
- Kept Space exclusively assigned to Freeze/Live and Enter assigned to opening or selecting the focused board cell.
- Added a right-click menu for every recorded attempt with all result variants and Delete attempt content.
- Kept the blue active-cell outline on the frozen attempt during judging and delayed its move to the next athlete until return to Live.
- Enabled the same right-click result menu on eligible blank cells; choosing a result creates a metadata-only cell that can be edited again without fabricating footage.
- Moved the next-attempt strip into the Competition Board and removed its Boys/Girls dropdown and Previous/Next buttons.

## Unified selection controls

- Fixed checkbox selected-state rendering with an explicit state map, stronger border contrast, accent fill, and a large high-contrast check mark.
- Added scalable rounded image backgrounds to every ttk button style, including default, navigation, header, judging, warning, and destructive actions.
- Reduced the rounded background footprint so buttons retain their compact pre-rounding height.
- Added rounded image fields to comboboxes and Windows compositor-rounded corners to combobox popups and File/View/Help menu windows.
- Preserved the same rounded component system through runtime dark/light theme changes.
- Recreated the family as compact pill-shaped buttons and dropdown fields with circular, visibly checked selection controls.

## Settings category navigation

- Added an always-visible scrollbar and mouse-wheel browsing to the Settings category sidebar, independent of each page's content scrollbar.

## Named camera selection

- Replaced the free-form camera index field in Settings with a read-only dropdown of available Windows Camera/Image device names.
- Dropdown labels retain the OpenCV index (`0 · Name`, `1 · Name`) so existing configuration and capture code stay compatible.
- Added a safe configured-index fallback when Windows camera enumeration is unavailable or an older configuration references a missing device.

## Settings column alignment

- Standardized setting rows into fixed Option, Description, and Value columns.
- Labels, impact badges, help text, checkboxes, entries, spinboxes, and selectors now align vertically across each Settings page.
- Added visible localized column headings and a wider minimum Settings workspace to prevent controls from drifting or wrapping into inconsistent positions.
- Added a localized description to every ordinary option and made Show setting descriptions immediately hide or restore the whole Description column.

## Timeline and compact-window layout

- Reserved full-height grid rows for the judging dock and status bar so neither can be partially hidden by the expanding media area.
- Moved timeline interaction instructions below the canvas into a dedicated row so the text cannot be clipped.
- Raised timeline targets to 30/60/90/60 Hz for Quiet/Balanced/High/Evidence and let a visible timeline drive the UI scheduler independently of preview FPS.

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
## UI polish — 2026-08-10

- Grouped Export, Delete, and Clear all temporary recordings into one equal-width muted action row.
- Removed numeric guide/ROI position fields from Settings; calibration is performed directly on the main video.
- Reworked Performance profile selection and clarified the evidence-quality boundary.
- Themed application-owned dialogs and confirmations for dark mode.
- Moved Hotkey Defaults above the table and removed Change/Clear toolbar buttons.
- Removed startup splash resize animations.
- Made recordings actions state-aware and reset the Competition Board to athlete 1 / attempt 1 after clearing all temporary recordings.
- Fixed Settings text layout: the glossary now uses responsive two-column term cards, and all explanatory text wraps to the space available in the current window instead of being cut off.
- Fixed Settings Value-column list controls overflowing on narrow pages; selectors now stay within the available column while retaining their full dropdown options.
- Made Export/Delete follow the exact capture selected in the Competition Board; selecting an empty cell fades and disables both actions instead of retaining the previous replay target.
- Made Settings and Competition Wizard dropdowns use normal rectangular native list styling, and reduced Settings Value-column field widths so controls stay on-screen.
- Added a 10-second startup input check with a progress bar and “Looking for input from all sources” text. Camera indices 0 and 1 are probed in the background; if no input arrives, Try again and Help with camera appear together.
