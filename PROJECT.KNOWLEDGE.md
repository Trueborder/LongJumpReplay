# Long Jump Replay — Project Knowledge

## Reusable activation keys, device history, and replay-only evaluation (2026-08-23)

- Email OTP remains the primary desktop activation method. The redesigned
  startup window uses the Evidence Desk cyan/dark visual language, removes the
  old offline machine-key route, offers a portal-managed key as the alternative,
  and directs a verified account without a purchase to tomaspisar.cz.
- Each active licence may have one reusable `NNNN-LLLL-RRRR` activation key.
  Digits, unambiguous uppercase letters, and unambiguous alphanumerics are
  generated with Web Crypto. D1 stores an HMAC verifier and AES-GCM ciphertext;
  `ACTIVATION_KEY_ENCRYPTION_KEY` is a Worker secret and must never be committed
  or printed. The portal hides the key on every load and offers explicit reveal,
  copy, and destructive regeneration controls.
- Regenerating a key deactivates only active devices whose activation method is
  `key`; email-activated devices remain active. The portal device table shows
  activation method, activation time, and last activity. Owner-only details put
  app/Windows/architecture, opaque identifiers, key generation, exact IP,
  country, and activity history behind an advanced disclosure. Only already
  deactivated device rows may be deleted.
- Migration `0006_activation_keys_and_device_activity.sql` adds activation-key
  storage, activation method and support metadata, plus device activity. Exact
  IP/country activity is disclosed in the privacy page and removed after 365
  days by a daily Worker schedule. Device deletion removes its detailed history
  immediately while retaining a minimal licence audit event.
- The local 72-hour evaluation is replay-only: camera capture, freeze, replay,
  and at most three standalone video exports remain available. Competition
  setup/board/rosters, verdicts/results, evidence and competition packages are
  forced off and guarded at their command entry points. A persistent banner
  identifies evaluation mode. A separate DPAPI-protected consumed marker makes
  the local trial one-use per Windows profile/machine on a best-effort basis;
  it is not tamper-proof against a local administrator deleting state.
- The website theme defaults to the system preference. Its control cycles
  System -> Light -> Dark and stores the override only under accepted preference
  consent. The preferred future activation upgrade is a short-lived portal/QR
  pairing approval; passkeys are a useful future portal-login upgrade.
- No code-signing change is included. A publicly trusted Authenticode certificate
  is the practical direct-download route; HTTPS, checksums and signed update
  manifests do not by themselves remove browser or SmartScreen warnings. See
  `docs/WINDOWS_CODE_SIGNING.md`.

## Email licensing and customer portal (2026-08-18)

- The authoritative licensing implementation is under `licensing-api/`. The
  production Worker is live at `https://api.tomaspisar.cz`; its live Stripe
  webhook is `/api/stripe/webhook`, and the account portal is served at
  `https://account.tomaspisar.cz/`.
- Production D1 is `longjumpreplay-licenses` (`afd54a54-bccb-494c-ac6d-377b00652c40`).
  Staging has a separate D1 database, `longjumpreplay-licenses-staging`
  (`6e80c8e7-b1da-4f60-9f76-bb3a0505d748`), configured for
  `api-staging.tomaspisar.cz` but awaiting separate test-mode secrets and
  prices before deployment.
- The customer flow is Stripe purchase -> webhook licence creation -> email
  OTP activation -> device-bound signed authorization. Anyone can sign in to
  the portal by email OTP before purchasing; an unlicensed account sees a buy
  prompt, and a later purchase with the same normalized email appears
  automatically. Portal codes are separate from activation codes. The portal
  uses an HttpOnly session cookie, lists licence/devices/invoices, supports
  device deactivation, and opens Stripe Customer Portal.
- Desktop activation sends an email code even before an active licence exists.
  These email-only challenges remain purpose-scoped away from portal login;
  after email verification, the app gives a localized no-active-licence result
  unless a subscription or lifetime licence exists at that point. A customer
  can therefore request a code before checkout and complete activation after
  checkout without weakening the device or plan checks.
- The desktop code-entry step has explicit Back and Activate controls; Back
  clears the pending code and returns focus to the email field without closing
  the activation dialog. The dialog recalculates its requested height when the
  code step opens or closes, so these actions remain fully visible instead of
  being clipped by the email step's initial fixed geometry. Dashboard device
  cards show the local activation time as well as the date. The verification
  code field filters typing and paste input to at most six ASCII digits.
  Transactional verification emails ship as branded HTML
  plus plain text, with cyan `APP ACTIVATION` and amber
  `CUSTOMER PORTAL LOGIN` purpose labels so the requested action is obvious.
- The portal has separate canonical routes: `/login` for passwordless email
  sign-in and `/dashboard/overview`, `/dashboard/licence`,
  `/dashboard/activation-key`, `/dashboard/devices`, `/dashboard/billing`, and
  `/dashboard/help` for authenticated account categories. `/dashboard`
  redirects to overview. The Worker redirects `/` according to session state,
  prevents authenticated users returning to the login screen, and protects all
  dashboard HTML with no-store responses. A persistent left-side category menu
  marks the active deep link; the small-screen version becomes a horizontal,
  touch-sized navigation strip.
- Portal entitlement display is based on active licence rows, not merely on
  purchase history. A canceled/refunded subscription remains visible as an
  inactive historical licence, while the overview shows no active licence,
  offers repurchase, reports zero available seats, and does not count devices
  belonging to the inactive plan as active.
- Commercial rules are fixed: maximum two devices; lifetime entitlement never
  expires; both lifetime and subscription authorizations refresh every 30 days;
  the app can work offline for 30 days; subscriptions receive seven days of
  grace after the paid period.
- Version 3.3 embeds the production licensing public signing modulus and adds a Licence
  & account panel in Settings linking to the portal. Do not print or commit the
  private signing key, webhook key, Stripe secret, Resend key, or pepper.
- Every frozen customer launch displays the licence check in the startup splash
  and asks the API to confirm that the device and plan are active. A successful
  check refreshes the signed 30-day authorization. Temporary connectivity,
  rate-limit, or server failures may use a still-valid signed authorization so
  an offline venue remains usable; explicit inactive-licence, missing-licence,
  or deactivated-device responses clear it and require activation. Tk updates
  remain on the main thread while the bounded network check runs in a worker.
- Website preferences use consent-gated first-party `site-theme` and
  `site-language` cookies; `ljr-consent` remembers accept/decline and every
  footer exposes Cookie settings so the choice can be changed. Portal auth uses
  a 30-day `ljr-portal-session` cookie with HttpOnly, Secure, SameSite=Lax and
  server-side hashed/revocable sessions. Private API responses are `no-store`.
- The production API/assets deployment has been smoke-tested, but a complete
  purchase-to-email-to-activation rehearsal still belongs on isolated Stripe
  test mode. A working Python 3.12 x64 environment is required before the
  desktop EXE can be rebuilt and release-validated.
- Version 3.3 adds an optional signed-update channel. Startup checks
  `https://files.tomaspisar.cz/latest.json` in a bounded worker while the splash
  remains non-blocking. The updater accepts only the stable LongJumpReplay
  product, an exact HTTPS versioned installer path, a valid RSA manifest
  signature, and matching byte length and SHA-256. Install, Skip this version,
  and Ask later are available; only the exact skipped version is suppressed.
  Update state is stored under `%LOCALAPPDATA%\LongJumpReplay`.

## Specialized adjudication architecture (2026-08-13)

- LongJumpReplay is a board-video adjudication appliance, not a replacement for AK2 or a complete athletics office. The primary workflow remains Capture -> Freeze -> frame inspection -> Valid/Foul/Review -> evidence -> next athlete; rankings, qualification/final administration, and official publishing are secondary and must stay modular.
- `src/adjudication.py` is the authoritative attempt-result store. Every frozen or placeholder attempt receives a stable adjudication ID, and verdict updates use a checksummed, fsynced write-ahead journal before the temporary attempt model changes. Atomic snapshots, a backup, journal replay, and recovery warnings protect decisions across crashes and corrupted snapshots.
- Temporary replay media and authoritative decisions have separate lifetimes. Deleting or expiring a recording marks its media unavailable but retains athlete/attempt context, verdict, selected frame metadata, board-line state, optional distance/wind, and evidence paths/hashes.
- Evidence preserves clean camera pixels separately from annotated derivatives and judge metadata. The explicit evidence package exports generic CSV and JSON interchange, a local session report, and available evidence; it never claims AK2 compatibility.
- Roster import is adapter-based (`CSV`, `XLSX`, `JSON`) and follows Parse -> Preview -> Validate -> Confirm -> Commit. Parsing cannot mutate the active roster. AK2-specific behavior must remain behind adapter boundaries and disabled/experimental until an official format or successful AK2 import verifies it.
- Distance and wind are optional manual metadata entered after a Valid verdict in a non-modal strip. All distance entry, board/recordings display, and generic interchange use whole centimetres; wind remains in m/s. Distance is never estimated from the camera. Saving or skipping the post-verdict measurement immediately returns Live and advances to the next athlete without an extra Space action, even when general automatic-advance/return settings are off.
- Right-clicking a Valid Competition Board attempt offers `Enter / edit measurement` and opens a focused popup for centimetres and wind. Popup edits update the durable record and board without changing the current athlete or Live/Replay state; non-Valid and empty cells keep this action disabled.
- The Competition Board is operational context: current/next athlete, attempt, verdict, optional distance, and immediate evidence reopening. Full official result books, complex rankings/tie resolution, result publishing, and speculative hardware integrations are deferred behind the core judging workflow.
- Local-only session reports measure attempts, verdicts, corrections, decision latency, missing evidence, skipped distance, recovery warnings, capture/drop statistics, buffer use, and UI timing. No personal telemetry is sent remotely by default.
- `docs/PRODUCT_STRATEGY.md` is the feature-priority boundary: CORE, USEFUL, DEFER, and REMOVE / AVOID. New competition-management work must be checked against it before it can displace adjudication reliability or performance work.

## Recordings context menu and explicit export (2026-08-13)

- The Recordings tab now supports right-click (and Shift+F10) on a recording with Open recording, Export, and Delete actions, matching the competition-board interaction model.
- Final video exports are explicit operator actions only: use the Recordings footer Export button or the recording context menu. Automatic final exports are not performed; temporary replay media remains in the managed cache so playback and retention continue to work.

## Local trial activation (2026-08-13)

- The standard customer activation dialog starts a machine-bound local 72-hour evaluation directly. It no longer asks for an email, marketing consent, or trial-service registration, so customers do not need Cloudflare, an API deployment, or an always-on computer.
- Local trial state uses the existing protected writable-data store and tracks the same three successful-export limit and clock-rollback guard. The old signed WSGI registration client/service remain available only for an explicitly customized legacy deployment.
- The customer EXE must be rebuilt from this source before distributing the change; existing frozen binaries still contain the previous email/API flow.
- Local-trial tests use a current issue timestamp rather than a historical fixed timestamp, so the 72-hour assertion remains valid as the calendar advances.

## Developer repository layout (2026-08-13)

- Active developer entry points are grouped under `scripts/build`, `scripts/run`, `scripts/setup`, and `scripts/maintenance`. Each moved script resolves and enters the repository root before accessing source, environments, tools, or output paths, so it can be launched from any working directory.
- Secondary documentation is stored under `docs/`; the root retains the primary `README.md`, license/notices, dependency metadata, application entry point, configuration, and developer-agent source-of-truth files.
- PyInstaller metadata lives under `packaging/`. `packaging/LongJumpReplay.spec` resolves source and asset inputs from the repository root and the optional Windows version metadata beside the spec.

## Localization expansion (2026-08-13)

- The language catalog now supports English, Czech, Slovak, Polish, Hungarian, German, Simplified Chinese, Hindi, Spanish, French, Arabic, Bengali, Portuguese, Russian, Indonesian, and Urdu. Settings shows each language by its native name and persists a stable two-letter code.
- English and Czech retain complete translation tables. Every additional locale translates the most frequently used operator controls and safely falls back to English for specialist copy that has not yet received a locale-specific translation; it must never fall through to Czech or expose an internal translation key.
- `src/language_catalog.py` is the single registry for supported codes, native names, selector options, normalization, and per-locale operator translations. Configuration validation, settings, the translator, timeline, video canvases, and competition board all consume that registry.
- Tests enforce the requested Central European languages, the broad world-language set, selector/code round trips, complete core override coverage, English fallback, and rejection of unknown language codes.

## Website Apple-inspired redesign (2026-08-13)

- The correct website checkout is `C:\Users\xpisa\LongJumpReplay\website\tomaspisar.cz`; the earlier `.ai_projects` website tree is separate and was not changed in this pass.
- `website/tomaspisar.cz/overrides.css` now applies an Apple-inspired material layer over the Evidence Desk system: translucent rounded navigation, system-ui body typography, calmer spacing, rounded evidence surfaces, one restrained primary-action treatment, and a frosted screenshot lightbox while preserving the live-cyan/decision-amber workflow language.
- `website/tomaspisar.cz/script.js` now provides scroll-aware header separation, accessible mobile-menu controls with outside-press dismissal, keyboard-operable screenshot opening with focus return from the lightbox, and optional IntersectionObserver reveals using opacity/transform only. Reduced motion and reduced transparency keep the site usable without decorative motion or blur.
- The homepage Featured software card keeps its LongJumpReplay copy and screenshot in separate full-width rows below 650px; the final mobile override in `website/tomaspisar.cz/overrides.css` must remain after the shared desktop product sizing rules to prevent horizontal overlap.
- UI/UX Pro Max's local search helper could not execute because the checkout's Python launcher points to a missing Python 3.12 installation; the persisted website design system and its quick-reference accessibility/motion rules were used instead. No framework or dependency was added.

## Documentation changes (2026-08-12)

- Added `docs/RECOMMENDED_SYSTEM_REQUIREMENTS.md` with a short bilingual hardware/software recommendation for event computers. It is a practical target rather than a formally benchmarked minimum and retains the requirement to test the complete camera setup before an event.
- The owner-only license generator formats machine-code input live as four uppercase hexadecimal groups, filters unsupported characters, and limits input to the 16-character machine identifier. Its final Tk cleanup tolerates a window that has already destroyed the application, preventing a close-time `TclError`.

## Audit changes (2026-08-11)

- Licensing tests now create an isolated temporary test signing key and patch the matching public modulus for their round-trip checks. Build and CI test runs therefore no longer require the ignored production `tools\.license_private_key.json`; the real key remains required only for the owner-only license administration tools.
- Pytest uses a unique per-process temporary root unless the caller supplies `--basetemp`, preventing `pytest-current` cleanup from colliding with folders created by an elevated or different Windows account.
- Pytest also validates Tcl/Tk library paths against the active Python installation before GUI modules load, preventing intermittent `tcl_findLibrary` startup failures in Windows customer-release runs.
- GUI test Tk creation retries transient Tcl/Tk library-initialization errors five times with a short bound, including Windows races that temporarily report an existing `tk.tcl` dependency as unreadable; a genuinely incomplete Python installation still fails explicitly after the bound.
- The clear-recordings GUI regression test waits a bounded period for the synthetic capture buffer to refill instead of treating one fixed scheduler timestamp as a failure.
- GUI shutdown stops capture before the attempt manager, preventing new frames from feeding attempt workers while teardown is already in progress.
- `scripts/run/RUN_TESTS.bat` runs non-GUI tests together and each `tests\*_gui.py` file in a fresh pytest process. All Windows build/test batch entry points use it so Tk interpreters and capture workers cannot leak across GUI test-file boundaries.
- `BUILD_CUSTOMER_RELEASE.bat` invokes its version reader with `-ExecutionPolicy Bypass`, matching the other release PowerShell calls so restrictive machine execution policy does not stop version detection before the build starts.
- The static sales site now uses a runway-control visual system and accurately describes the Capture/Freeze/Replay/Decide workflow. English/Czech copy is valid UTF-8, public download language says Windows installer rather than MSI, and `BUILD_SITE.ps1` reads transformed HTML/CSS with explicit UTF-8 encoding so deployable output cannot reintroduce mojibake. Every page loads the shared SVG `TP` favicon, and the About page uses a four-part bilingual narrative covering approach, focus, process, and current work. The LongJumpReplay product gallery uses the current project screenshots for the main station, recordings list, and competition board; the static fallback images use the same current captures.
- The `website/tomaspisar.cz` source now carries a persisted UI/UX Pro Max design system and an Evidence Desk visual layer: Barlow typography, timing-black/chalk themes, live-capture cyan, review amber, a restrained take-off-line/timecode hero, flat evidence panels, active navigation, SVG controls, declared screenshot dimensions, and keyboard-friendly menu/lightbox behavior. The bilingual content, product metadata, installer link, and dark/light theme persistence remain shared through the existing configuration and script.
- The publish-ready installer is deployed from `website/files.tomaspisar.cz/LJR_setup.exe` and linked as `https://files.tomaspisar.cz/LJR_setup.exe`. The build pipeline emits the versioned `LongJumpReplay-Setup-<major.minor>.exe`, so publishing renames it to the stable unversioned `LJR_setup.exe`; the download URL therefore does not change between releases. The site links come from `installerUrl` in `website/tomaspisar.cz/site.config.js`, which `script.js` applies to every `[data-installer-url]` element, and the hardcoded `href` fallbacks under `website/tomaspisar.cz/download/` must be kept in sync with it.
- `src/config.py` preserves malformed settings as `.corrupt` backups and starts from validated defaults; `config_from_dict` still raises for direct callers that need strict validation.
- `AttemptManager.delete()` protects collecting/encoding/exporting attempts from destructive races. Export copies use temporary destinations before replacement, and cache-size directory scans are throttled and invalidated after cache mutations.
- Encoded replay reads use a bounded per-attempt LRU plus a sequential decoder position. This preserves frame stepping while reducing repeated random seeks during playback/comparison.
- `VideoCanvas` keeps a fixed Tk canvas item set and updates it in place. The timeline remains governed by its existing pooled-item contract.
- Evidence capture resolves the selected attempt frame and writes PNG/JSON artifacts atomically; it must not use `_displayed_bgr` as the source of truth.
- The native `ReplayCoordinator` keeps frozen review bounded by removing the oldest post-freeze frames when the selected frame reaches the retention boundary. Native execution still requires a machine with the .NET SDK.

## Developer workspace cleanup (2026-08-11)

- Removed obsolete Codex onboarding prompts, the redundant customer README source, stale self-test/runtime logs, and the unused file inventory.
- Build outputs, local virtual environments, native `bin`/`obj` folders, caches, and test reports are ignored by Git and are not part of the source tree. The active local `.venv` remains available to the developer but is no longer tracked.
- Packaging now uses `README.md` as the customer readme source and still emits `README.txt` in portable/installer outputs.

## Customer release cleanup (2026-08-10)

- The normal customer interface no longer exposes Diagnostics, operator/setup mode, synthetic test-source selection, advanced troubleshooting settings, or the internal cache-folder shortcut.
- Synthetic capture, self-tests, recovery compatibility, and diagnostic implementation remain available to development and support paths; they are not removed from the runtime code.
- The startup splash no longer shows a developer credit, and the portable customer build no longer copies synthetic or self-test launcher files.
- The initial camera startup overlay still says it is looking for input from all sources. The startup probe checks camera 0 and camera 1 and switches the main live capture to the first working camera; a settings-triggered restart carries the explicitly selected camera index into startup so the overlay identifies camera 0, camera 1, or the configured device.

> Primary handoff document for human developers and Codex. Read this file before changing code.

## 1. Project identity

- **Project:** Long Jump Replay
- **Current source version:** 3.3.2
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
13. **All registered interface languages are supported through a deterministic English fallback.** New user-facing strings must go through `src/i18n.py`; frequently used operator controls should also be added to each locale override in `src/language_catalog.py`.
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
  - complete English/Czech translation dictionaries, locale-aware translator, and deterministic English fallback.

- `src/language_catalog.py`
  - supported language codes and native names;
  - settings selector conversion and language normalization;
  - core operator translations for additional world languages.

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

The Windows build scripts detect a stale `.venv` whose interpreter points to a different machine, leave it untouched, and create a fresh `.venv-build-*` Python 3.12 environment. Single-file builds disable UPX compression to reduce bootloader/antivirus extraction failures. The portable folder remains the supported customer path when Windows cannot unpack a one-file executable.

The portable PyInstaller spec uses `COLLECT`/`exclude_binaries=True` so `scripts/build/BUILD_PORTABLE.bat` produces and tests `dist\LongJumpReplay\LongJumpReplay.exe`; it must not regress to an untested one-file `dist\LongJumpReplay.exe`.

Single-file build commands write generated specs under `build\generated`; they must not overwrite the portable `packaging/LongJumpReplay.spec`.

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

### Collaboration authorization

- The project owner has authorized Codex to make all in-scope LongJumpReplay edits and install required build tools without repeated approval prompts.

### Customer installer and updates

- `scripts\build\BUILD_RELEASE.bat` is the supported 3.3 portable payload entry point. It runs source and GUI tests plus source/frozen self-tests before refreshing the exact `release` directory.
- `scripts\build\BUILD_INSTALLER.bat` compiles `packaging\LongJumpReplay.iss` with Inno Setup. It preserves the 3.1 AppId and installs under `Program Files\LongJumpReplay` with Start Menu, optional Desktop, Add/Remove Programs, uninstall, and in-place upgrade support.
- Frozen runtime state remains under `%LOCALAPPDATA%\LongJumpReplay`, so installation and upgrades do not require writing to Program Files.
- The previous offline machine-bound customer key route is retired and is no
  longer reachable from startup. Paid customer activation uses email OTP or the
  reusable portal key; both result in the same server-issued, device-bound
  signed authorization. Shared RSA primitives remain because trial,
  authorization and updater signature verification still depend on them.
- The first-run license dialog is independent of the withdrawn Tk root, centered, raised, focused, and temporarily topmost so frozen Windows launches cannot wait invisibly for activation.
- The static sales site is under `website`; edit `website\site.config.js` to change the contact email, price, domain, or installer URL, then run `website\BUILD_SITE.ps1` to create the deployable `website\dist` folder. The build must preserve UTF-8 for Czech copy and symbols, rewrite source-only asset paths, and keep the 390 px mobile layout free of horizontal overflow.

### Source setup

- `scripts/setup/INSTALL_WINDOWS.bat`

### Run

- `scripts/run/RUN_SYNTHETIC.bat`
- `scripts/run/RUN_CAMERA.bat`
- `SELF_TEST.bat`

### Portable release

- `scripts/build/BUILD_PORTABLE.bat`
- output: `release\LongJumpReplay-3.3.0-Windows-x64.zip`

### Single EXE

- `BUILD_SINGLE_EXE.bat`
- supported, but not the recommended distribution format.

### Inno Setup installer and R2 publication

- `scripts\build\BUILD_INSTALLER.bat` is the one-click installer entry point. It rebuilds the tested portable payload, derives the version from `src/__init__.py`, generates Windows file metadata, and writes `release\LongJumpReplay-Setup-<semantic-version>.exe` plus its SHA-256 sidecar.
- `scripts\release\PUBLISH_RELEASE.bat` signs `latest.json`, verifies it locally, uploads and downloads immutable versioned R2 objects for hash verification, updates `LJR_setup.exe`, then publishes `latest.json` last. `ROLLBACK_RELEASE.bat <version>` restores an already verified archived release.
- `packaging\.update-signing-private.pem` is ignored and must be backed up offline. `src\update_public_key.py` is the corresponding embedded public key. This update key is separate from the authorization signing key.
- The website reads the signed channel metadata for its displayed version and versioned installer URL, while retaining `LJR_setup.exe` as a no-script fallback. See `docs\RELEASING.md`.

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

- Video zoom rendering crops the source to the visible canvas region before resizing. The virtual full-image bounds still drive pan, guide, and ROI geometry, while OpenCV/Pillow temporary images remain approximately viewport-sized instead of growing with zoom up to 10×.
- Every application start restores all View-menu workspace elements: recordings, Competition Board, timeline, live preview, and status bar. Timeline restoration clamps saved or newly shown panes to a 220 px usable target so its ruler, detail view, scrollbar, and hint do not reopen collapsed at the bottom; larger saved heights remain intact.
- The Competition Wizard opens directly into its five-step setup flow without a teaching or simulated-practice path. Setup uses Simple event, Qualification + final, and Judge-only replay templates; adapts its pages to the chosen format; validates dependencies inline; keeps optional judging as the default; requires an explicit Keep/Clear decision for existing temporary recordings; and shows non-blocking capture/buffer/cache readiness with Settings and camera-help handoffs. Wizard results contain only `CompetitionConfig`, which is merged into the latest `AppConfig` so Settings changes made while the wizard is open cannot be reverted.
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

- `scripts\build\BUILD_INSTALLER.bat` is the one-click customer installer command. Existing content in the exact `release` folder is replaced only after source and GUI checks plus source/frozen self-tests succeed.
- `scripts/build/BUILD_RELEASE.bat` invokes `scripts/build/BUILD_PORTABLE.bat --folder-only`, validates the tested payload, and adds `LICENSE.txt`. Its only distributable output is the loose `release/LongJumpReplay` application folder; it must not create `ProductFinal`, a ZIP, or a checksum sidecar. Pass `--no-pause` for automation.
- `scripts\release\PUBLISH_RELEASE.bat` is the production publication entry point. It publishes immutable versioned R2 objects, verifies downloaded bytes, refreshes the stable alias, and exposes the signed manifest last.
- The loose `release/LongJumpReplay` payload includes `LongJumpReplay.exe`, the complete `_internal` runtime tree, `README.txt`, `LICENSE.txt`, and the frozen self-test report.
- The payload can be copied beneath `C:\Program Files\LongJumpReplay`, but the application still uses `%LOCALAPPDATA%\LongJumpReplay` for writable per-user configuration, license data, cache, exports/evidence, runtime logs, and crash logs. Program Files is therefore not the only storage location; do not remove the AppData directory after installation.

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

- Hotkey capture uses Tk's platform-specific Alt state mask: on Windows, Num Lock no longer turns a plain key such as `v` into `Alt-v`, while genuine Alt combinations remain supported.
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

## Lifetime additional-computer purchases (2026-08-20)

- Active lifetime licences keep their original `licenses` row and may add computers through the authenticated portal. Subscription, inactive, and already-full licences never receive the purchase option.
- Lifetime licences start at 2 computers, cost 4,990 Kč, and can grow to 10 total computers. Marginal one-time prices are computer 3: 1,490 Kč; computer 4: 1,290 Kč; computers 5-10: 990 Kč each. The Worker calculates totals; the browser never supplies a price.
- `POST /api/portal/additional-computers` validates the portal session, customer ownership, active lifetime type, integer quantity, and remaining capacity. It creates an official Stripe-hosted Checkout Session using one server-generated CZK line item per marginal computer and metadata for customer, licence, quantity, product, and purchase type.
- Migration `licensing-api/migrations/0005_additional_computers.sql` adds a unique Stripe-session purchase ledger. Webhook fulfillment requires `payment_status=paid`, verifies the existing Stripe signature, conditionally updates `max_devices` to stay at or below 10, and records an auditable `additional_computers_purchased` event. Duplicate sessions/events are ignored and abandoned or failed payments do not change entitlements.
- Test coverage includes marginal totals, breakdown rendering inputs, TypeScript type checking, portal routing, and the existing licensing tests. A Stripe test-mode rehearsal remains required before production deployment; configure test secrets and webhook delivery separately and never commit their values.

## Account portal login fix (2026-08-20)

- The login page must load `account-state.js` before `account.js`. The shared account script destructures `window.LJR_ACCOUNT_STATE` during startup; omitting this dependency prevents the submit handler from registering and leaves the email form visually unchanged.
