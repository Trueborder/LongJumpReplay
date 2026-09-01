# LongJumpReplay changelog

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
