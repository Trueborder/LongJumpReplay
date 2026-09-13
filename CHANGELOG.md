# LongJumpReplay changelog

## 6.2.9 - 2026-09-13

- Prevents the topmost startup window from remaining over the application
  after camera and UI polling begin.
- Refreshes startup presentation with compact dark rounded progress bars and
  controls while preserving truthful overall and current-stage progress.
- Keeps the original athlete artwork and adds a brief Windows-aware fade-in
  that follows the system animation preference.

## 6.2.8 - 2026-09-13

- Adds live App CPU and App RAM performance graphs with separate readable axes.
- Keeps Performance monitoring active while the system is paused and records
  zero camera/buffer FPS while capture is stopped.
- Keeps settings search global so Advanced settings remain discoverable from
  the Simple view.

## 6.2.7 - 2026-09-12

- Publishes the current recording library, persistent Capture Mode recordings,
  asynchronous thumbnails, recording verdict actions, and the synchronized
  attempt editor.
- Compacts the default timeline layout while keeping vertical resizing and
  frame navigation responsive.
- Centers application popups, shows source-aware file-loading feedback, and
  keeps the competition board visible when switching from Judge-only mode to
  an event.

## 6.2.6 - 2026-09-10

- Improves take-off board and foul-line detection with light-board, red-track,
  geometric, and dark-strip evidence while retaining fast local processing.
- Refines full-shoe selection around the board, exposes lightweight detection
  diagnostics, and separates observed contact from estimated top-down pixels.
- Keeps the fullscreen split review visible with a neutral **NOT AVAILABLE**
  result when no trustworthy shoe is detected instead of opening the editor.
- Prevents Take-off Assist from selecting an empty post-departure frame and
  clamps configured lead offsets to frames where the shoe remains visible.
- Adds a short non-blocking reveal for the completed projection and verdict.

## 6.2.5 - 2026-09-10

- Makes the final fullscreen split review the first window shown by the button
  or Enter shortcut, with the frozen original immediately visible on the left.
- Removes the separate fullscreen loader from this path. Frame loading,
  analysis, and reconstruction update one progress bar in the split review,
  and the computed image is inserted into the right panel in place.

## 6.2.4 - 2026-09-10

- Opens the final fullscreen split review before reconstruction starts, with
  the original camera frame visible immediately and the computed panel filled
  when the projection finishes.
- Keeps one monotonic progress bar across analysis and reconstruction stages.

## 6.2.3 - 2026-09-10

- Shows the frozen original camera frame immediately in the fullscreen
  projection loading surface while the computed top-down result is prepared.
- Adds a configurable `Open top-down projection` application hotkey, enabled
  by default on Enter.

## 6.2.2 - 2026-09-10

- Opens Top-down projection in fullscreen immediately after Freeze, with a
  truthful determinate loading bar while frames and the projection are built.
- Removes the optional Advanced camera profile from the projection workflow;
  normal board calibration remains the only required setup.
- Makes Judge-only replay a review-only surface by hiding competition-board,
  verdict controls, roster navigation, and related keyboard actions.
- Removes the obsolete keyboard and zoom instruction strip below the timeline.

## 6.2.1 - 2026-09-09

- Extends the logarithmic timeline zoom down to a one-second detailed view and
  lets the board-calibration editor replace its startup snapshot with the
  latest live camera frame while preserving normalized edit points.
- Opens a skippable board-calibration review after the camera produces its
  first frame on every launch. Saved geometry must be previewed and confirmed;
  otherwise board and take-off-line detection supplies editable suggestions.
- Replaces the bottom-right Board setup control with a guided four-corner board
  and four-corner take-off-line editor, and adds independent View toggles for
  the thin competition overlays.
- Reworks projection review around the exact replay frame currently displayed:
  the frame chooser and separate Board/Overhead compute modes are replaced by
  one automatic flat top-down projection.
- Improves shoe segmentation with multi-reference foreground recovery, shadow
  suppression, bounded GrabCut refinement, concave contour preservation, and
  confidence-aware `REVIEW ORIGINAL` fallback.
- Enlarges the unified top-down result, moves verdict and confidence outside
  the evidence raster, hides idle progress, and adds a sharp cursor-following
  magnifier plus brush-assisted shoe-edge correction.
- Reduces review-time CPU work with coarse-to-fine Take-off Assist scanning, a
  bounded decoded-frame cache, optical-flow neighbour contours, cached lens
  maps, pre-queue retention filtering, and single-pass top-down rectification
  without changing evidence or export formats.
- Shows the athlete countdown in tenths of a second, starts a new competition
  on athlete 1 / attempt 1, keeps the wizard confirmation page stable, and
  defaults the live camera guide outlines off.
- Automatically opens a full-screen original-versus-computed top-down review
  after analysis, with a clear VALID / FOUL / ON THE LINE / REVIEW ORIGINAL
  badge and actionable status messages when computation cannot proceed.

## 4.0.0 - 2026-09-06

- Adds a recording workflow that can run without the rolling buffer: press
  Record and Stop, then open the completed recording from Captures.
- Adds timeline zoom from 0.5 seconds to 10 minutes, a visible-span readout,
  and local clock timestamps with millisecond precision.
- Adds ShuttleXpress actions for Record/Stop, latest Capture, and hold-to-play.
- Makes the operator interface more compact so the camera remains dominant.
- Adds an editable video-file source path with a native file picker and shows
  Windows-detected friendly camera names while retaining camera indices
  internally.
- Keeps an already-visible timeline at exactly the same size when Settings is
  applied without changing the layout.

## 3.3.10 - 2026-09-01

- Removes manual width and height settings for resizable panels; drag the
  dividers directly and keep the layout remembered.
- Fixes competition-board athlete labels and makes the board instructions
  responsive when the window is resized.
- Adds a truthful modal progress indicator while checking for updates.
- Keeps licence-key copy confirmation private with the shorter “Copied” message.

## 3.3.9 - 2026-09-01

- Rebuilds the free evaluation as a replay-only 72-hour showcase with three
  standalone video exports and immediate expiry locking.
- Adds the public contact form with Turnstile protection and email delivery.
- Adds licence diagnostics and a safe support summary in Settings.
- Makes the desktop shortcut unconditional in the Windows installer.

## 3.3.8 - 2026-08-24

- Update-system test release with no application behaviour changes.

## 3.3.7 - 2026-08-24

- Starts and confirms the Windows installer before closing the running app, preventing a stalled shutdown from silently blocking installation.
- Keeps the update dialog open with a manual installer path if Windows rejects the launch, and records an Inno Setup installation log.

## 3.3.6 - 2026-08-24

- Preserves Settings modality after up-to-date and update-error messages close.

## 3.3.5 - 2026-08-24

- Adds a localized Check for updates action to Licence & account in Settings.
- Keeps Settings modal and keyboard focus intact after closing an available-update dialog.

## 3.3.4 - 2026-08-24

- Replaces simulated loading animations with truthful Windows-style startup, activation, update, camera, export, and pause progress feedback.
- Keeps activation indicators visibly moving and shows the startup window for at least two seconds before activation opens.
- Restores the timeline at a usable height so the camera remains visible at startup.
- Prevents transient pane measurements from producing Settings errors or blocking Exit.

## 3.3.3 - 2026-08-24

- Adds reusable portal-managed activation keys and clearer email activation guidance.
- Limits the free 72-hour evaluation to replay testing rather than competition operation.
- Improves activation feedback and customer device management.
- Keeps website downloads on the current stable installer while protecting immutable update releases from accidental replacement.

## 3.3.2 - 2026-08-19

- Automatically filters the activation verification-code field to six ASCII digits when typing or pasting.

## 3.3.1 - 2026-08-19

- Keeps the Back and Activate actions fully visible when the email activation dialog advances to verification-code entry.

## 3.3.0 - 2026-08-19

- Adds secure in-application update checks during startup without delaying the judge station.
- Adds one-click verified downloads with Install, Skip this version, and Ask later choices.
- Adds a reproducible Inno Setup installer and rollback-safe Cloudflare publishing workflow.
- Keeps the website download version synchronized with the published release manifest.

## 3.2.0 - 2026-08-18

- Added Stripe-backed email activation and the customer account portal.
- Added licence verification at every application startup with an offline authorization window.
