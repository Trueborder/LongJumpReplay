# Long Jump Replay — Project Knowledge

## Automatic take-off advisory (2026-09-14)

- `src/automatic_takeoff.py` owns the CPU-only automatic pipeline. A bounded 16–18 Hz, roughly 192-pixel board-ROI gate runs on a dedicated latest-frame worker and never queues work on the camera thread. It pins the detected instant through the existing RAM-buffer `AttemptManager`; it does not introduce another capture or recording pipeline.
- A detected attempt is evaluated on at most three reduced frames plus bounded references. The existing Take-off Assist candidate search, shoe-outline estimator and calibrated nearest-contact-edge measurement are reused. Temporal agreement returns `valid`, `foul`, or the safe `review` fallback; clipped geometry can support a clear crossing but cannot support Valid.
- Automatic advice is persisted separately from `AttemptDecision`. It never writes the official competition verdict. The video shows a symbol, persistent `ASSIST` badge and 1.5-second semantic border flash; likely Foul can play the Windows warning sound. Smart mode stays Live after likely Valid and opens the decisive replay frame for Foul or Review.
- The feature is opt-in under Settings → Board & Take-off Assist and remains covered by the existing `takeoff_assist` entitlement. Advanced settings expose the bounded timeout, duplicate-event cooldown and opt-in anonymous local correction capture. Local samples are stored under the writable application data directory and are never uploaded.
- Camera-shift correlation disarms automatic advice and requires the operator to confirm board calibration again. Automatic processing also disarms while capture is paused, replay is open, calibration is missing, or the licence lacks Take-off Assist.
- `validation/manifest.example.json` is schema 2. `tools/detection_validation.py` remains compatible with schema 1 and now measures both decisive-frame error and advisory classification. Athlete media and reports with private paths remain outside Git. A release must report confident-error and Review rates by camera, light, footwear, frame rate and visibility class; Review is deliberately preferred over an unsafe confident answer.
- The supplied 25 fps MS Video-1 AVI is useful for regression development but is not a sufficient training/validation set. With its current partial-board view and the current manual calibration, the bounded pipeline returns Review rather than inventing a shoe outline; the measured analysis itself completes in about 1.2 seconds on this development PC. More manually annotated complete-board examples are required before enabling the feature by default.

## Website organization (2026-09-13)

- The authoritative public website source is `website/tomaspisar.cz`. Public pages remain at the root; product pages now live under `products/long-jump-replay/` and `products/relaylab/`.
- General legal content is under `legal/privacy/`. LongJumpReplay-specific privacy content remains under its product directory because it covers the desktop application's licensing and activation flow.
- Shared public assets are centralized under `assets/`: CSS is split into tokens/global/components plus page styles, JavaScript is split into shared components/account/page modules, and product screenshots are under `assets/images/long-jump-replay/`.
- Account pages remain under `website/tomaspisar.cz/account/` because the separate `licensing-api` Worker serves that directory as its static asset root. They consume shared CSS and JavaScript from the public site's `assets/` URL.
- There is no fake static `api/` tree: public RelayLab adapter endpoints are handled by `website/main-site-worker.ts`, while authentication, licensing, Stripe and protected downloads remain in `licensing-api/src/`.
- Old `/software/...` and `/privacy` URLs are permanent redirects in `website/main-site-worker.ts`; the old full-width product row was replaced by a compact contextual strip. `/welcome/` remains because it has unique post-purchase/download guidance.
- The global website header no longer exposes a redundant Downloads link; download actions remain in product and account content. LongJumpReplay product pages use a compact rounded context strip with Overview, Licensing, and Privacy links. RelayLab does not show a one-item local menu.
- `website/design-system/` is source documentation only and stays outside the public output. `website/wrangler.jsonc` owns the public site Worker; `licensing-api/wrangler.jsonc` owns the account Worker boundary.

## Portal registration and migration (2026-09-13)

- Customer registration is served at `account.tomaspisar.cz/register`. It verifies email ownership with a separate, HMAC-protected, expiring and attempt-limited challenge before collecting first name, surname, optional club name, and a 12-character minimum password containing a letter, number, and symbol.
- The authenticated dashboard includes `/dashboard/profile`, backed by the existing CSRF-protected profile and password endpoints. It edits first name, surname, optional club, and password; the verified account email remains read-only. The login screen keeps password sign-in primary, places recovery next, and hides OTP and registration under `Show other options`; mode-specific back controls must remain hidden on the normal sign-in view.
- The desktop activation dialog is choice-first: customer-portal QR pairing is the prominent recommended action, email verification and reusable-key activation are grouped as secondary alternatives, and the limited 72-hour evaluation has its own quiet section. Keep all activation callbacks and keyboard behavior connected when changing this composition.
- Portal OTP login no longer creates customer rows for unknown email addresses. Existing email-only customer rows are still supported, but their first verified portal access is routed through the registration completion gate before dashboard access.
- Migration `licensing-api/migrations/0011_portal_registration.sql` adds `portal_profiles` and `portal_registration_challenges`. Passwords remain in `customer_password_credentials`; OTP remains the recovery path. The setup token is stored only as a hash and is kept in browser memory, never in a URL or persistent storage.
- The account Worker serves the registration page from `website/tomaspisar.cz/account/register/`; shared CSS and `assets/js/account/account.js` handle the bilingual responsive flow. Dashboard data returns only setup-state metadata until the required profile/password is complete.

## Resize-only rendering bindings (2026-09-13)

- `src/theme.py::bind_resize_only()` centralizes the Tk `<Configure>` guard:
  callbacks run when a widget's width or height changes, but not when a
  toplevel is merely moved. This prevents expensive layout and raster redraws
  while dragging windows.
- The main window now suspends video/timeline rendering only during a real
  resize. Settings page canvases, responsive descriptions, Performance graphs,
  the timeline, video canvases, board calibration, and Top-down Projection use
  the same helper. Settings pages remain cached; navigation only shows or
  hides existing frames and never rebuilds them because of window movement.

## Screen-centred application popups (2026-09-12)

- `src/theme.py::configure_popup()` waits for the popup to be mapped, then measures the complete decorated Win32 window (including title bar and borders) and centres that outer rectangle on the full monitor containing its parent. This preserves the dialog's final requested size and works on secondary monitors.
- Packaged Tcl/Tk may return fullscreen as the string `"0"`; the shared helper parses that state explicitly instead of relying on Python string truthiness. Licensing and Top-down Projection windows that create `Toplevel` directly use the same utility. Deliberate full-screen review/projection surfaces are excluded.
- `src/theme.py` owns the desktop button system. New controls select a semantic variant through `button_style()` (`secondary`, `primary`, `success`, `danger`, `warning`, `neutral`, `toolbar`, `icon`, `destructive`, plus the four judge roles). Every role defines normal, hover, pressed, focus, selected, and disabled rendering in both themes; compatibility aliases keep older extensions and late-created dialogs consistent.

## Recording review integration and compact timeline (2026-09-12)

- The Recordings panel is a direct attempt-library view, without a separate search field. It shows a larger recording number and thumbnail, supports Open/Edit/Export/Delete plus the competition verdict actions, and uses the verdict colour for the active row.
- Double-clicking either a competition-board attempt or its recording opens the same attempt editor. The editor synchronizes replay first and edits verdict, distance and wind through the existing adjudication store; measurements remain available only in competition mode after a Valid verdict.
- Recording thumbnail preference is persisted in attempt metadata. Opening Top-down Projection commits the currently displayed frame; otherwise thumbnail generation falls back to the Take-off Assist candidate and then the frozen frame. Thumbnail extraction stays asynchronous and its cache key includes the selected frame.
- Event templates explicitly restore competition controls and board visibility after Judge-only replay. The notebook tab must be changed back to `normal` even when Tk still reports the hidden tab in `tabs()`.
- The timeline defaults to a compact 164-pixel target with a 150-pixel minimum, while the existing sash remains vertically resizable and stored non-legacy user heights remain respected.
- Camera startup feedback is source-aware: file input shows `Loading file source`, while camera input keeps the device-search wording.

## One-second review and live calibration snapshot (2026-09-09, 6.2.1)

- The logarithmic timeline detail range is exactly 1 to 3600 seconds and still
  defaults to 60 seconds. Existing saved values are clamped into that range.
- The board-calibration editor can replace its initial startup snapshot with
  the latest frame from the continuously running camera. Existing board and
  foul-area points are preserved in normalized image coordinates, including
  across a resolution change; the operator may adjust them or run detection
  again. A stale automatic-detection result from the replaced frame is ignored.
- The athlete timer preserves whole-second state thresholds but displays a
  tenth-second countdown (`MM:SS.t`) while running. A fresh application session resets the
  competition focus to the first enabled group, athlete 1, attempt 1.
- The competition wizard review page is static after rendering; readiness is
  refreshed only by the explicit Refresh action, avoiding repeated widget
  destruction and visible flashing.
- Main camera guide and board-outline visibility defaults are off while board
  detection remains enabled. The projection editor can still show outlines on
  demand.

## CPU-efficient review pipeline (2026-09-09, 6.2.1)

- The capture thread applies `store_every_nth_frame` before the encoder queue.
  Frames intentionally excluded from the rolling replay are still published as
  the latest live frame, but no longer allocate queue work or evict a frame
  that should be retained.
- Long Take-off Assist windows use a coarse reduced-ROI scan followed by an
  exact consecutive-frame refinement around the detected peak. Short windows
  retain the original full scan. Logs report window frames, frames actually
  decoded, stride, duration, candidate and confidence.
- `AttemptManager` keeps a bounded twelve-frame decoded LRU shared by replay
  stepping and projection loading. Cached packet frames retain their original
  timestamps; completed-video frames retain the derived media timestamp.
- Top-down reconstruction treats the selected measured outline as
  authoritative. Neighbouring observations first propagate it with sparse
  optical flow; full GrabCut shoe segmentation is limited to two failed-flow
  fallbacks. Diagnostics distinguish tracked observations and full refinements.
- Camera-profile undistortion maps are cached per resolution and calibration.
  The clean top-down board raster is rectified once, then copied for overlay
  rendering. Mouse inspection remains visualization-only.
- Temporary MP4 and manual export formats are unchanged. Direct MJPEG packet
  muxing is intentionally deferred until a bundled, validated muxer is
  available, because changing temporary media compatibility is higher risk
  than the processing optimizations above.

## Unified top-down review and calibration (2026-09-09, 6.2.1)

- The projection window keeps one operator-facing result. The original frame
  uses roughly 40% of visualization height and the larger Top-down projection
  uses roughly 60%; there is no second competing projection panel.
- Saved four-corner foul-area calibration is reused in the projection editor,
  with its two-point centreline derived only for measurement compatibility.
  Source overlays use consistent visible widths and remain independently
  hideable.
- Shoe detection searches beyond the physical board so a side-view heel and
  upper are not cropped away. The manual shoe editor adds an optional brush:
  paint once around the shoe and release to snap a resampled contour to nearby
  image edges without rerunning detection.
- Mouse zoom is a throttled local magnifier, normally 3x and adjustable from
  1.5x to 8x. It tracks the real image point under the cursor with light
  smoothing, ignores letterboxing, clamps edge crops, redraws overlays sharply,
  and never triggers analysis. Fullscreen retains cursor-anchored wheel zoom
  and adds drag pan plus double-click reset.
- Once automatic top-down compute completes, a separate fullscreen review
  compares the original frame with the computed top-down image and places the
  verdict outside both rasters. Any key closes that review; the normal
  single-result workspace remains underneath for editing.
- Verdict and confidence sit outside the raster as one LEGAL, FOUL, or
  UNCERTAIN badge. Observed geometry is solid green, estimated geometry dashed
  yellow, and the image contains no overlapping status text. The single
  modeless determinate bar is visible only while real compute stages advance;
  idle state is a compact completion line with measured duration.

## Compact desktop interface density (2026-09-07)

- The Tk interface applies a non-compounding `100 / 130` density ratio to the
  native Windows/Tk scale. Text and character-sized controls become about 23%
  smaller while retaining the computer's DPI factor. Shared button padding,
  inputs, tabs, table rows, and checkbox indicators are also
  tightened consistently; changing themes does not apply the ratio again.
- The public product page describes support for compatible high-frame-rate
  cameras, including qualified 120 FPS capture when the camera, driver, and
  computer support it, in both English and Czech.
- The product-page Requirements section publishes the practical bilingual event
  target from `docs/RECOMMENDED_SYSTEM_REQUIREMENTS.md`: Windows 11 x64, recent
  Core i5/Ryzen 5 or better, 16 GB RAM, an SSD with 10 GB free, Full HD display,
  and a USB 3 camera capable of 720p60 (with 120 FPS preferred for detailed
  review). It remains a recommendation, not a formally benchmarked minimum.

## Local top-view projection (2026-09-07)

- Frozen attempts can open a modeless Top-view projection window. It ranks
  seven nearby frames from retained packets or cached MP4, uses a local
  classical OpenCV motion/contour estimate with manual polygon correction,
  and projects the foot through a saved four-corner pad homography plus
  foul-line endpoints.
- Calibration is tied to the camera source, backend, device/file identity,
  and frame resolution; mismatches require recalibration. After the first
  camera frame on every launch, a skippable guided editor opens. A matching
  saved setup is presented for review and must be previewed and confirmed;
  otherwise the app detects the board and take-off line automatically. The
  operator can drag four thin board corners and four corners surrounding the
  take-off line, preview the clean result, and return to editing. No
  dimensions are entered; the PESMENPOL board dimensions 1201 × 340 mm supply
  a 120.1 × 34 cm top-view scale, while its 100 mm height is irrelevant to the
  planar homography. Older saved custom dimensions remain compatible.
- The view is decision support only. It never changes Valid/Foul or replaces
  the original camera evidence.
- Candidate ranking weights proximity to the Take-off Assist timestamp above
  raw motion, and compares chronological neighbouring frames rather than only
  consecutive frame indices. Foot extraction suppresses illumination-only
  darkening, searches an expanded calibrated-board zone, and scores compact,
  edge-rich contours so broad athlete shadows do not win by area.
- Take-off Assist uses the same colour-aware local-motion segmentation. Both
  newly cast shadows and regions where a shadow has just moved away are
  suppressed before temporal peak scoring, while dark shoes with hard edges
  remain eligible.
- Projection foot extraction derives its search bounds from the calibrated
  board rather than the narrower Take-off Assist ROI, uses clean frames from
  the attempt boundaries as background references, and weights proximity to
  the calibrated foul line. A real 1920 × 1080 cached attempt confirmed that
  the outline moved from a board speck to the shoe while Take-off Assist kept
  the correct event frame. Private recordings are never committed as fixtures.
- Measurement uses the detected or manually corrected sole/contact outline,
  never the shoe centre or decorative upper. The 120.1 cm physical axis is
  selected parallel to the calibrated foul line and the 34 cm axis is selected
  perpendicular to it, independent of camera rotation and corner-click order.
  The result is the minimum signed edge distance: positive clear, zero within
  uncertainty, and negative for the deepest crossing. Calibration, resolution,
  segmentation, and accepted-fit variation contribute to the displayed
  uncertainty. The board-centre side is inferred as legal and the persisted
  Flip legal side control corrects unusual installations.
- Candidate thumbnails are limited to the five most likely frames centred on
  the predicted frame, shown at about 160 × 100 with horizontal scrolling.
  Selecting one updates the planar board projection immediately and starts a
  cancellable local reconstruction worker. Switching frames or closing the
  window cancels and discards stale results; Tk widgets remain main-thread only.
- The optional Overhead shoe view fits a bounded parametric sole and explanatory
  upper using OpenCV/NumPy only, with a hard five-second deadline. Its single
  modeless determinate progress bar advances on real stages (preparing frames,
  isolating shoe, fitting model, rendering). Observed surfaces retain source
  colour, hidden surfaces use neutral shading, and the view is labelled
  Estimated shoe footprint. Low-confidence and timed-out fits are rejected while the
  corrected board projection remains available. Neither view decides Valid or
  Foul.
- The former bottom-right Board setup group is no longer shown. View → Board
  calibration reopens the same guided editor, while independent View toggles
  make the thin board and take-off-line overlays optional during competition.
- Advanced camera profiling is optional. A bundled print-at-100% 8 × 5-inner-
  corner checkerboard with 25 mm squares can produce a local lens profile from
  at least three sharp, distinct views; ordinary use still needs only the
  two-step board/foul-line calibration.

## Light-only website appearance (2026-09-06)

- The public website and account portal use one permanent light appearance.
  Theme controls, dark/system preference resolution, theme cookies, and dark
  palette branches were removed; old stored theme preferences are discarded.

## LongJumpReplay 4.0 recording and timeline release (2026-09-06)

- Version 4.0.0 adds explicit Record/Stop capture mode, ShuttleXpress capture
  controls, timeline zoom and millisecond wall-clock labels, a denser operator
  workspace, selectable video-file paths, and Windows friendly camera names.
- Applying Settings does not reposition an already-visible timeline sash. The
  release build generates a clean embedded default configuration and never
  packages the development computer's mutable root `config.json`.
- GUI release groups run in separate Python processes and receive one bounded
  fresh-process retry for transient Tk/synthetic startup races. A group that
  fails twice still stops the release.
- Release 4.0.0 was published on 2026-09-06. The 50,827,748-byte installer has
  SHA-256 `CCCCDCFAF65A52F7E6B6C310A93B54232920583324DB95DD42C398A5F390F3C3`.
  The release gate passed 157 non-GUI tests, 60 GUI tests in 17 fresh-process
  groups, source and frozen synthetic self-tests, installer construction, and
  public post-upload hash verification. The production licensing Worker
  deployment is `381c0b6e-3534-4866-819d-ae5b23ddaa40`; the main-site Worker
  deployment is `3e6ad8ea-3ae6-4cf0-9570-4dda40f6cbda`.

## Panel sizing, competition-board feedback, and update checking (2026-09-01)

- The Settings > Views page no longer exposes recordings-panel width or
  timeline-height inputs. Users resize both panes directly with their dividers;
  the measured sash positions remain persisted for compatibility and are still
  restored on startup.
- Competition-board instructions now wrap below the target controls as the
  window narrows. The board target formats the numeric athlete number before
  applying the `02d` translation placeholder.
- Manual update checks use a modal, single indeterminate horizontal progress
  bar until the real background check returns. Download progress remains a
  separate determinate bar with its existing cancellation behavior.

## Replay-only trial, contact form, and licence diagnostics (2026-09-01)

- The local 72-hour evaluation is now governed by a centralized capability
  policy: capture, freeze, replay, saved still frames, and three standalone
  video exports are allowed; competition setup, rosters, judging, verdicts,
  results, evidence, and competition packages are blocked. A live expiry poll
  locks the workspace and opens paid activation; the consumed marker remains
  non-resettable by the customer. See `docs/TRIAL_LICENSING.md`.
- The public Contact page uses a labelled form with name, email, topic, and
  message fields, including a dedicated club-licence / better-price topic.
  `licensing-api` sends validated submissions to
  `info@tomaspisar.cz` with the visitor as Reply-To, using origin checks,
  Turnstile, a honeypot, and D1 rate-limit metadata without storing messages.
  The public site key is configured in `website/tomaspisar.cz/site.config.js`
  and the private `CONTACT_TURNSTILE_SECRET` Worker secret is present in the
  production Worker configuration.
- Settings > Licence & account now shows version, licence state, signed
  authorization timing, device limit, last successful check, trial status,
  and a safe support-summary clipboard action. Authorization files remain
  backward-compatible when the new check timestamp is absent.
- Release 3.3.9 creates the desktop shortcut unconditionally by removing the
  optional `desktopicon` task. The installer is built and published through the
  standard release workflow after the source, GUI, frozen, and installer checks
  pass.
- The shared public and account-site header is fixed to the viewport while
  scrolling. The body reserves its desktop/mobile header space, and the mobile
  navigation remains positioned below the fixed header.
- Customer-facing support, product, licensing, privacy, and contact copy now
  uses a consistent plural company voice in English and Czech. The About page
  remains intentionally personal because it describes Tomáš directly.

## Account portal readability redesign (2026-09-01)

- The account portal keeps its existing email-OTP recovery flow and now also
  supports optional password login, alongside the same dashboard routes,
  API behavior, themes, and bilingual content while presenting a quieter,
  more readable Evidence Desk layout.
- Repeated informational card groups were removed from Overview, Licence,
  Computers, and Billing. Secondary activation, billing, support, security,
  and sign-in guidance is retained behind native keyboard-accessible
  `<details>` disclosures.
- The account portal test suite asserts that the removed information-card
  pattern does not return; all website tests passed after the redesign.

## Stable customer downloads and immutable releases (2026-08-24)

- Website installer buttons always keep the configured
  `https://files.tomaspisar.cz/LJR_setup.exe` stable alias. The signed release
  manifest may update the displayed version, but it must not replace manual
  download links with the immutable versioned updater URL.
- `Publish-Release.ps1` checks the public customer-facing versioned installer
  before any upload. Matching bytes and their signed archived manifest may be
  reused; different bytes abort publication and require a version increase.
  All post-upload verification also uses the public URLs, so CDN-visible stale
  bytes cannot pass merely because the R2 control path contains newer bytes.
  Public verification requests use unique query strings so a pre-upload 404
  cannot mask a newly uploaded immutable object at the edge.
- Release 3.3.3 establishes a new immutable URL after two different 3.3.2
  installers had previously been published under the same versioned key.
- Release 3.3.4 was published on 2026-08-24 with installer SHA-256
  `88D2C8075D5E99FE5A75F3DF09EFB634A5E4F5B85480D0EEFACC10FA0F73F6B4`.
  The public signed stable manifest, immutable installer, and stable alias were
  downloaded and hash-verified after publication.
- Release 3.3.5 was published on 2026-08-24 with installer SHA-256
  `62C0C6E7F11641EB49C53CA70473374408BAB36D14FC7D9D2B62AC35292BF898`.
  It adds the Settings update-check action and preserves Settings modality for
  available-update dialogs.
- Release 3.3.6 was published on 2026-08-24 with installer SHA-256
  `9EEC47E69A8140C3B2BE07B17181FE484B9FFC20169E758C5759AF16A552C50D`.
  It also restores the Settings modal grab after current-version and update-error
  messages close.
- Release 3.3.7 was published on 2026-08-24 with installer SHA-256
  `B235564A8739D8430EA1FDCBA4608CB9ACC865508C5546CB9B5FD3F1D232B490`.
  It removes the unbounded pre-installer process wait.
- Release 3.3.8 was published on 2026-08-24 with installer SHA-256
  `AFDE4140A55A9F68100265F3D7B986603046DE04FF294F392713CEBABFBC6B16`.
  It is a metadata-only update-system test and the current stable channel
  release; it contains no application behaviour changes from 3.3.7.
- Release 3.3.9 was published on 2026-09-01 with installer SHA-256
  `2430865CA2D95315713DC86629DD334305C88672DB2AEA0AEC7C499F54DCF643`.
  It includes the replay-only trial policy, public contact form, licence
  diagnostics, and unconditional desktop shortcut. The production licensing
  Worker deployment is `2db96058-9faf-4ca6-82ed-e75068dddf0b`; the main-site
  Worker deployment is `d6367f96-5eb7-4b03-9da6-0f8f2d63170f`.

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
- Manual key entry inserts separators immediately after the fourth and eighth
  accepted characters and restores the Tk insertion cursor after formatting,
  so the next character stays to the right of the separator. Portal Copy works
  while the key remains masked by retrieving it only for the clipboard action.
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
- The post-payment `/welcome/` page places an amber download safety alert beside
  the installer button. It explains how to keep an uncommon download and use
  SmartScreen's More info / Run anyway path, while telling customers to verify
  the official `files.tomaspisar.cz` source and `LJR_setup.exe` filename.

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
- The portal has separate canonical routes: `/login` for password or
  passwordless email
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
  Update state is stored under `%LOCALAPPDATA%\LongJumpReplay`. The installer
  is launched and confirmed before the app begins shutdown; Inno Setup uses
  `/FORCECLOSEAPPLICATIONS`, writes `updates\update-install.log`, and relaunches
  the installed app. If Windows rejects the launch, the app remains open and
  shows the verified installer path for manual recovery.

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
- **Current source version:** 6.2.8
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
16. **Take-off Assist may show a Valid/Foul/Review advisory but must never write the official verdict.** A human remains responsible.
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
- Camera settings show Windows friendly device names while retaining the OpenCV index internally. Selecting the File source enables a directly editable video path and a native file picker; the saved path is opened by `VideoFileSource` after restart.
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
Licence & account includes a localized Check for updates action. It uses the same signed stable-channel checker as the Help menu; update results are parented to Settings and restore its modal grab and keyboard focus when dismissed.

Every ordinary setting row follows the same three-column contract: Option (fixed width), Description (flexible), and Value (fixed width). Column headings are visible and localized. Every row has a useful localized description; `general.show_tooltips` immediately hides or restores the complete middle column, including its headings, without moving the Value column inconsistently. Checkboxes align to the same Value-column origin as entries, spinboxes, and selectors; individual label or description length must not move a control horizontally.

Checkboxes, comboboxes, combobox list popups, and classic Tk menus are themed as one component family. Checkbox indicator images are owned by `ThemeManager` for their full Tk lifetime. Dark/light theme application must also restyle existing File/View/Help and nested menus; native-looking defaults must not reappear after a runtime theme change.

All ttk buttons use the shared small-radius (6 px), one-pixel-border nine-slice backgrounds from `ThemeManager`; they must remain desktop-shaped rather than pill-shaped and must not impose a larger minimum height than each semantic role requires. Standard actions and judging actions are approximately 32â€“34 px, while compact toolbar actions remain smaller. The neutral widget backing must not refill the transparent corners of bright semantic images. Comboboxes and menu buttons share the same fill, border, typography, and focus hierarchy. Checkboxes use a circular accent indicator with a visible white check. On Windows, mapped classic menu windows and combobox popdowns request DWM rounded corners. Checkbox tests must verify both Tk selected state and different rendered checked/unchecked pixels so an invisible logical selection cannot regress unnoticed. The Settings category sidebar has its own always-visible scrollbar and mouse-wheel navigation, independent of the scrollable contents of each page.

The competition target strip belongs inside the Competition Board tab and shows only the projected next athlete number and attempt; the standalone special-results/More button, old Boys/Girls selector, and Previous/Next buttons must not return. Special results remain available through board/recording context actions and configured shortcuts. Every board cell is focusable. While the Competition Board tab is selected and visible, plain arrow keys move the persistent blue, softly pulsing focus regardless of which child widget owns focus; they never step replay frames in that context. Enter opens recorded content or selects an empty cell. Space always remains Freeze/Live. Modified arrows and all unrelated configured shortcuts keep their normal actions. Freeze keeps the board's active outline on the recorded athlete/attempt throughout judging; only a successful return to Live advances it to the next rotation cell. Right-clicking either a recorded or eligible blank cell exposes all decision variants. Choosing a status on a blank cell creates a metadata-only, zero-frame placeholder without changing the current athlete; Delete attempt content is enabled only when a record exists.

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

For release 3.3.8, the Windows source suite passed **149 tests**, the 17 isolated GUI modules passed **56 tests**, the website suite passed **17 tests**, and the licensing Worker passed **19 tests** plus TypeScript checking. Source and frozen synthetic pipeline self-tests both completed attempt MP4/export with no remaining workers before the Inno Setup installer was built. This does not replace visual GUI inspection on the fresh VM, a four-hour soak, physical webcam/120 FPS camera, full native feature parity, and actual ShuttleXpress testing.

## 14. Build and release

Wrangler state created under `scripts/release/.wrangler/` is machine-local deployment cache and must remain ignored; release scripts and manifests are versioned, but generated Cloudflare account cache is not.

### Collaboration authorization

- The project owner has authorized Codex to make all in-scope LongJumpReplay edits and install required build tools without repeated approval prompts.

### Customer installer and updates

- `scripts\build\BUILD_RELEASE.bat` is the supported 3.3 portable payload entry point. It runs source and GUI tests plus source/frozen self-tests before refreshing the exact `release` directory.
- `scripts\build\BUILD_INSTALLER.bat` compiles `packaging\LongJumpReplay.iss` with Inno Setup. It preserves the 3.1 AppId and installs under `Program Files\LongJumpReplay` with Start Menu, Desktop, Add/Remove Programs, uninstall, and in-place upgrade support.
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
- Every application start restores all View-menu workspace elements: recordings, Competition Board, timeline, live preview, and status bar. Timeline restoration waits until the main window has real mapped geometry, then clamps the pane to a 220 px usable target while preserving enough camera space; larger valid saved heights remain intact. Transient out-of-range sash measurements are repaired before Settings or persistence, and can never prevent bounded Exit.
- The Competition Wizard opens directly into its five-step setup flow without a teaching or simulated-practice path. Setup uses Simple event, Qualification + final, and Judge-only replay templates; adapts its pages to the chosen format; validates dependencies inline; keeps optional judging as the default; requires an explicit Keep/Clear decision for existing temporary recordings; and shows non-blocking capture/buffer/cache readiness with Settings and camera-help handoffs. Wizard results contain only `CompetitionConfig`, which is merged into the latest `AppConfig` so Settings changes made while the wizard is open cannot be reverted.
- Settings and Competition Board scrolling now handle Windows and Linux wheel/button events consistently, refresh scroll regions after content changes, and use themed scrollbar states. Settings Hotkeys puts Defaults above the table; double-click changes a row and the right-click menu restores one default with duplicate protection. A first-run guided tutorial is persisted in `general.onboarding_completed` and can be reopened from General settings. Applying camera/live-buffer changes asks whether to restart immediately; the relaunch preserves the script or frozen executable arguments. Board guide width is passed to all video canvases and evidence overlays instead of using a fixed preview width.

- Judge controls are grouped into frame review and judging categories. The four verdict buttons use equal widths and the shared neutral/green/red/amber judge variants with a persistent selected state; board setup is handled by the startup calibration editor rather than a bottom-right control.
- Verdict controls are greyed whenever there is no active frozen attempt to judge (including Live and system-paused states).
- Competition-board scrolling handles Windows and Linux wheel events, including horizontal Shift-wheel scrolling, while preserving keyboard cell navigation.
- Attempt export uses one modeless status-bar indicator: it begins indeterminate while the requested attempt is still encoding, then switches to real copied/total bytes as soon as the temporary MP4 size is known. Camera pause/resume feedback is delayed briefly so fast transitions do not flash, and synchronous recording clearing has no progress bar.
- Camera startup and resume use one modeless indeterminate overlay because frame-arrival progress cannot be measured. The status bar no longer animates at the same time. After the existing ten-second bound, the overlay is replaced by Try again and Help with source/index, permissions, competing-app, capture-mode, and diagnostic guidance.
- The packaged application uses PyInstaller's boot splash with the unchanged `assets/long_jump_splash.png` artwork before Python initialization, then closes it only after the detailed Tk startup window paints. Source launches begin with the detailed Tk window after Python/Tk initialization.
- `py app.py --splash-preview` opens that splash by itself for visual review and exits when the user presses Escape; it does not start camera, shuttle, buffer, or attempt workers.
- Startup uses typed progress events and two determinate bars only for its real overall/current-task hierarchy: settings/logging 0–10%, components 10–30%, licence/update checks 30–50%, interface construction 50–90%, and services/readiness 90–100%. It never advances from elapsed time or reaches 100% before the main window paints and required workers start.
- Startup phase history is available through a keyboard-reachable Details disclosure. Only `general.progress_details_expanded` is persisted; history and diagnostics are not. Fatal startup failures stop the bar and offer Open log and Exit without showing a stack trace in the window. Before activation opens, the painted startup window remains visible for at least two seconds; time already spent loading and checking the licence counts toward that minimum.
- Email and reusable-key activation use modal indeterminate bars that visibly move while the server is processing because response duration cannot be measured truthfully. Update downloads use real bytes, checksum/preparation phases, stable rate/remaining-time details after a reliability window, and safe cancellation that removes `.partial` files and restores dialog controls.
- The main control dock has one larger Freeze/Live toggle. Frame review and judging buttons are enabled only for a frozen attempt and use the same disabled/faded treatment; Not decided uses a neutral pending style rather than black. Board Setup is a matching labeled group, and the system pause button/mode badge share a fixed width.
- The athlete countdown duration is managed in a dedicated Athlete timer settings category with a Low performance-impact badge.
- On the Competition Board, Up/Down may move between athlete rows; Left/Right are reserved for replay frame stepping after Freeze and never change the selected attempt column.
- Export, Delete, and Clear all temporary recordings share one equal-width muted action row. Board calibration position/size fields are intentionally absent from Settings and are changed in the guided four-corner editor. All application-owned dialogs use the current ThemeManager palette.

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
- Settings no longer edits guide/ROI positions or dimensions numerically. Those values remain owned by the guided Board calibration editor; Settings keeps visibility and line-width controls plus plain-language guidance.
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

## Website light-theme material correction (2026-08-25)

- The Apple material tokens in `website/tomaspisar.cz/overrides.css` must have explicit light-theme values. Reusing the dark translucent `--apple-surface` values in light mode produces broad muddy-gray gradients across product, signal, fact, contact, download, FAQ, and cookie surfaces.
- Light mode uses ivory translucent surfaces, restrained teal-gray borders, and softer neutral shadows. Dark mode tokens, layout, typography, responsive rules, and the dark product screenshot remain unchanged.
- The header theme control shows its current localized preference: System, Light, or Dark. The explicit choice is mirrored to session storage immediately so same-tab page navigation cannot reset it; accepted preference cookies additionally retain it across browser sessions and use the `tomaspisar.cz` domain so the main site and account portal share the choice. Every page with the control applies the cookie-or-session preference in its head before body paint.
- The 2026-08-25 production deployment is main-site Worker version `f6f8a35b-6cf1-45d1-80c2-a8ed11e5b2a2` and account/API Worker version `87742899-4c14-41f6-98d5-8e9a3e8a2d36`. Cache-bypassed live CSS/JavaScript matched the local assets, `/login` contained the early theme bootstrap with the required account-state dependency order, and `/health` returned HTTP 200.

## Activation feedback and device deletion state (2026-08-23)

- The portal distinguishes an inactive licence from an actually deactivated device. A stored active device on an inactive licence is labelled `Inactive licence` and must be deactivated before Delete is offered; only rows whose device status is `deactivated` may be deleted.
- Email-code and reusable-key activation run blocking network work on daemon threads while Tk polls results on its own event loop. Their theme-aware `Modal.Horizontal.TProgressbar` indicators are 10px high and animate for the full `Working…` request; duplicate actions are disabled, and controls recover after an error.
- Every `[data-installer-url]` button creates and opens the same focused browser/SmartScreen safety dialog immediately after the installer download begins, including `/welcome/`, `/download/`, and `/download/ljr/`. Closing the dialog restores focus to the button that started that download. The purchase-confirmation page also keeps the guidance visible beside its original button and uses a consistent plural company voice in English and Czech.

## Recording modes and operator timeline (2026-09-06)

- LongJumpReplay now supports a restart-applied `buffer` or `capture` recording mode. Buffer mode preserves rolling replay and Freeze; Capture mode disables ring-buffer persistence and saves only explicit Record/Stop sessions through the existing attempt/export pipeline.
- Capture mode records the current competition assignment, auto-stops at the configurable maximum (default 10 minutes), finalizes safely on shutdown, and adds Record/Stop markers to the saved attempt timeline. Capture packets retain monotonic media time plus a wall-clock timestamp for local `HH:MM:SS.mmm` display.
- The timeline has direct drag zoom, a visible span label, and local wall-clock playhead/tick labels. Applying Settings leaves an already-visible timeline sash untouched and only positions it when the timeline is newly shown. The current zoom limits are defined by the newer timeline evidence-layer section below.
- ShuttleXpress defaults are Live, Record/Stop, unused, latest Capture, and hold-to-play from the current position; button mappings remain configurable. Compact operator styling reduces control/panel density so the camera remains dominant.

## Timeline evidence layers and Settings information architecture (2026-09-07)

- The timeline zoom is logarithmic from exactly 1 second to 60 minutes and defaults to 60 seconds. Legacy zoom bounds are migrated by clamping them into this supported range. Drag changes stay in memory while moving and persist only when the drag ends; wheel changes use a short settling debounce.
- Recorded media is a labelled blue band with wall-clock start/end boundaries. Take-off Assist shows its actual analysed interval in violet, and its predicted frame uses an amber diamond/line plus a fixed ±100 ms confidence zone whose fill strength follows the confidence value. Manual markers, Freeze, and the fixed-centre playhead retain different shapes or line treatments so colour is not the only cue. The compact overview mirrors recorded, analysed, and predicted ranges without creating canvas items per refresh.
- Take-off Assist attempt persistence includes the first and last timestamps actually analysed. Older attempt JSON remains compatible because both fields are optional.
- Settings has eight task-oriented pages: General; Camera & recording; Competition; Judging & evidence; Board & Take-off Assist; Workspace & controls; Licence & support; and Advanced. General opens first. Existing configuration keys remain available, while low-level camera, codec, and performance controls live under Advanced.
- Settings search matches English and Czech labels, descriptions, page names, option values, and explicit keywords. `Ctrl+F` focuses search; arrow keys navigate results; Enter opens, scrolls to, focuses, and briefly outlines the setting; Escape clears search. Searching never marks the configuration as changed.
- Shared styled text and custom canvas/overlay text retain the compact-interface baseline. Settings keeps its fixed footer and existing window size; the Czech Browse control uses the same existing compact text treatment so it remains inside the minimum window.
- A failed Take-off Assist now raises a persistent `! Take-off Assist failed` warning beside the Freeze/Live controls for the active frozen attempt. Missing frames, no detected peak, analysis errors, and below-threshold confidence all use this failure path; returning Live, selecting another attempt, or receiving a valid candidate clears it.
- Capture-quality warnings no longer insert a banner above the workspace. The status row carries a compact warning such as `! LOW FPS 80/120 | DROPS 3`, preserving the camera's vertical workspace while keeping the operator signal visible.

## Corrected overhead and board projection (2026-09-08)

- Board projection and overhead rendering now use the foul-line orientation to map the physical 120.1 cm axis horizontally, so reversed/rotated corner orders do not transpose the board or move the fitted sole away from the source shoe.
- Optional camera profiles (including radial distortion coefficients) are applied before rectification. The Advanced camera wizard remains optional; the normal four-corner board workflow is unchanged.
- The review window asks for Board projection or Overhead shoe before analysing frames, keeps one truthful modeless determinate progress bar, and suppresses candidate thumbnails that do not contain a sufficiently confident shoe estimate.
- The frozen-attempt action is now **3D projection**. It first shows a modal determinate loader while a bounded shortlist is decoded, then opens a dedicated left-thumbnail/right-preview frame-selection page.
- Confirming a frame starts a second cancellable automatic-analysis loader. Board edges, the foul line, and a smooth sole/contact outline are detected before the projection workspace opens; unreliable analysis returns to frame selection without inventing geometry.
- The workspace shows the annotated original frame above two equal blank panels. Board projection and Overhead shoe each start only from their own Compute button and share one truthful modeless determinate progress surface. Back cancels stale work and returns to the cached frame selection.
- The former Set up board, Find board edges, Estimate foot, initial view-choice, and view-switch buttons are not part of the active 3D projection window. Automatic overlays remain editable; geometry changes invalidate both results and restore both Compute buttons.
- Clicking an Edit board, Edit foul line, or Edit shoe control enters precision mode: the annotated source frame expands to the available workspace and the projection panes temporarily hide. The same control exits precision mode and restores both panels; the optional Mouse zoom checkbox enables the cursor magnifier while editing.
- Take-off Assist combines shadow suppression, compact dark-object presence, and onset selection so it favours the first usable foot frame instead of a late trailing motion peak.
- 3D projection startup reuses the bounded frames that already passed Take-off Assist's compact-shoe gate (or the same five-frame temporal window if the assist is still finishing). It no longer decodes separate background references or reruns ranking and multi-frame shoe segmentation before opening the chooser; frame confirmation still performs the authoritative board, foul-line, and contact-outline analysis.
- Projection compute workers now report unexpected failures back to the Tk worker queue, so one failed board or overhead fit cannot leave the other Compute button permanently blocked. Empty rectification results fall back to a visible board crop instead of presenting an all-black panel.
- The workspace toolbar is grouped into navigation, editing, and calibration labels with larger controls. Editing hides the other actions and exposes Done plus the optional mouse zoom; the zoomed editing crop includes the board, foul-line, and shoe overlays.
- Frame confirmation uses two hidden temporal anchors outside the five visible candidates, applies physical shoe-size scoring while choosing contours, and retries against individual clean references when a median background is contaminated by the athlete. A remaining size mismatch opens the correction workspace with a clear warning instead of blocking the operator before Edit shoe is available.
- Projection results normalize OpenCV arrays before passing them to Pillow/Tk, and the worker-queue poller now survives display exceptions so a failed first view cannot prevent the other Compute action. Rectification also checks how much of the warped board maps to real source pixels and falls back to the visible calibrated crop when the homography would produce a mostly black board.
- Mouse zoom is available throughout the projection workspace, not only while a point-editing tool is active. Its checkbox clears the lens immediately when switched off, changes the source cursor, and reports the current on/off state.
- If automatic board, foul-line, or shoe-outline analysis fails after frame confirmation, the frame chooser preserves any geometry already found and shows **Set up manually**. The recovery workspace supplies editable board/foul handles, focuses the failed layer, accepts the first three points of a completely manual shoe outline, and asks the operator to re-analyse after correcting the failed geometry; provisional guesses are not persisted until edited.
- Projection canvases use Tk-native Windows cursor names (`hand2` for clickable results and `crosshair` in fullscreen); CSS cursor names such as `zoom-in` raise a Tcl error on Windows and must not be used.
- Shoe extraction supplements shadow-suppressed motion with non-shadow Lab colour/lightness change, joins nearby sole fragments, and strongly prefers physically typical shoe dimensions instead of treating every contour inside the broad plausible range equally. This prevents small heel or board fragments from outranking a complete sole.
- The projection workspace has a **Show outlines** switch. It removes board, foul-line, sole, and estimated-upper geometry from the source and both computed views while retaining the source imagery and measurement text; the active layer remains visible during editing. Mouse magnification remains rendered and follows the dragged point throughout a drag.
- Overhead reconstruction no longer rejects a selected outline because its apparent calibrated length or width falls outside a fixed shoe-size range. The local contour is scale-normalised only for fitting, while its original signed position relative to the foul line remains the classification evidence; camera distance and non-standard board size therefore do not block rendering.
- Active board and overhead projection images present **VALID**, **FOUL**, or **ON THE LINE** instead of centimetre clearance. Fullscreen uses the same classification. This is visual decision support and does not write the official Valid/Foul adjudication automatically.
- Automatic-analysis recovery is named for the failed layer. In particular, a foul-line failure returns to frame selection with **Set foul line manually**; it opens the selected frame in precision mode with two visible red endpoints and explicit instructions to place both endpoints, finish editing, and re-analyse.

### Unified top-down projection (2026-09-09)

- The projection action now uses the exact frame currently displayed in replay. Take-off Assist is not allowed to replace the operator's frame; up to three neighbouring frames on either side are hidden segmentation references only.
- The frame chooser and separate Board projection/Overhead shoe compute workflow are no longer active. The window opens directly into one Top-down projection workspace and starts one automatic background computation after analysis.
- Shoe extraction compares against every temporal reference, joins separated shoe regions, refines with bounded GrabCut, preserves concave contours, suppresses shadows, and treats calibrated dimensions only as geometry—not as a plausibility gate.
- Manual analysis failure stays on the current frame and opens the failed board, foul-line, or shoe editor directly. Completing an edit invalidates stale output and automatically recomputes the unified projection.
- Reconstruction results now carry observed, estimated, and contact masks plus a confidence-aware verdict. Low-confidence contact is labelled **REVIEW ORIGINAL**; only credible contact geometry drives the advisory classification.
- The unified result remains a flat board-plane view. The original frame remains authoritative and reconstructed regions are explanatory only.

### Board, shoe, and result refinement (2026-09-10)

- Automatic board calibration combines adaptive light-colour segmentation with rectangularity, opposing-edge geometry, red-tartan context, local brightness contrast, and optional dark-strip evidence. Analysis is bounded to a 1100-pixel working image and remains compatible with neutral indoor fixtures and partially visible boards.
- Foul-line selection scores both dark-strip coverage and transverse gradient support in the rectified board instead of selecting a Canny response alone.
- Shoe candidates are generated only inside the board-anchored search region. Selection uses each contour's nearest point to the foul line and board, relative completeness, connected shape, edge support, shadow content, and penalties for tartan, straight board markings, and exposed skin. Toe contours use a finer approximation than the former outline.
- Detection logs include board, foul-line, and shoe timing plus shoe candidate count and confidence. A lightweight Detection debug switch shows the board, foul area, shoe ROI, candidate contours, selected contour, longitudinal axis, heel, and toe without re-running analysis.
- The top-down raster keeps rectified observed pixels unchanged. Only the model-only area receives a blurred, low-opacity colour approximation with a dashed outline, and the contact mask is derived from the observed outline rather than the completed model.
- The fullscreen comparison reveals the completed projection with a 220 ms opacity transition followed by a 160 ms result-text transition. Both run through Tk's event loop without delaying computation, respect Windows client-area animation settings, and are cancelled when the review closes.
- If automatic shoe detection produces no trustworthy outline, the calibrated board projection still computes from the detected board and foul line inside the existing full-screen split review. The fallback raster is cropped to the rectified board pixels with no embedded title/verdict labels or reserved formatting area; the split-review badge communicates **SHOE NOT DETECTED**. Exiting split review reuses that already-computed board image in the unified workspace panel instead of exposing an unusable overhead Compute action. A toolbar **Show split review** action reopens the comparison from the cached result without recomputation and remains disabled until a result exists. Overhead reconstruction remains disabled until a shoe outline is supplied, and the manual shoe-edit path is preserved. Board and foul-line failures retain their existing manual calibration recovery.
- Take-off Assist now requires a compact shoe-presence signal in the selected frame instead of allowing the smoothed disappearance-motion peak to select an empty frame. Its relative-size gate accepts close-up shoes occupying up to 24% of the board ROI, rejects thin markings, and uses colour contrast as well as darkness. Configured lead-frame offsets are clamped to frames that passed the visible-shoe gate, and the cached projection references remain the original visible frames.

### Operator workflow and performance maintenance (2026-09-11)

- The main header now has a fourth Camera selector beside File, View, and Help, separated by a small gap. It lists detected cameras and routes a selection through the normal restart-safe camera settings path.
- The calibration wizard remains the shared board and take-off-line reconstruction editor. Its preview state places Confirm calibration before Back to edit, and returning from frozen replay animates the timeline back toward live media.
- Top-down visualization mouse magnification defaults off for new windows. The Settings dialog renders its General page first and defers secondary page construction until the event loop is idle, reducing perceived open latency.
- Performance buttons are presented as task-oriented Smooth live, Balanced judging, Fast review, Evidence review, and Custom modes. These modes adjust presentation workload only; retained evidence quality remains explicit.
- Take-off Assist waits briefly for pinned packets before declaring failure, and its configured Quick Review remains the smooth candidate-review path. Physical ShuttleXpress validation still requires connected hardware; parser, debounce, mapping, and action-queue behavior are covered by tests.

### RelayLab swimming application (2026-09-10)

### Recording library and product boundaries (2026-09-12)

- The Python/Tkinter application remains the authoritative LongJumpReplay desktop product. `native/` is a separate preview implementation and must not be treated as a second production pipeline.
- Live capture continues through `CaptureEngine` and `TimeRingBuffer`; Capture Mode is retired. The supported workflow is buffer -> Freeze attempt -> background encode -> persistent export, so clearing temporary cache never removes an exported recording.
- `AttemptManager` writes durable session metadata atomically, stages persistent video under `recordings/.incomplete/`, recovers finished recordings on restart, and leaves temporary cache cleanup independent of the recording library. Incomplete persistent markers are removed during recovery without touching unrelated user files.
- The recordings panel is the existing operator surface: it has a metadata search field, saved/temporary media state, date/time, duration, thumbnail fallback, asynchronous cached thumbnails, Open/Export/Delete actions, and an Open recordings folder command. Thumbnails are generated by `RecordingThumbnailWorker`, never by the Tk event loop.
- Mutable paths are resolved through `src/portable_paths.py` and `AppDataPaths`: cache, recordings, exports/evidence, adjudication, and recording thumbnails. Existing configured absolute paths remain valid; the new default recordings directory is additive and does not migrate or delete old files.
- `ProfessionalTimeline` keeps its pooled fixed-playhead renderer and animated return-to-live transition. The default vertical pane is compact (208 px usable baseline, down from the former 220 px) while the existing sash remains resizable within the configured bounds.
- Performance profiles are real presentation/analysis workload controls. They do not silently reduce retained evidence quality. The explicit Older PC profile remains the only frame-dropping tradeoff.
- ShuttleXpress remains optional HID input routed through the shared action queue: jog steps frames, the spring-loaded shuttle selects attempts, and configurable button actions preserve keyboard/controller independence. Physical device behavior still needs testing on a connected Contour unit.
- The website login remains email OTP backed by `/api/portal/request-code` and `/api/portal/verify-code`; the centered LongJumpReplay login composition adds code resend, change-email, expired-code, loading, and success states without changing authentication architecture. The logged-in portal continues using the same account/licensing backend and responsive site tokens.
- LongJumpReplay and RelayLab are separated by product routes and modules inside the shared static website because the current deployment paths and worker routing are shared. Do not move them into independent repositories or change deployment roots without updating the site worker and release configuration together.
- Paid feature checks are capability-based through `authorization_permits()`. Existing grants without a feature list remain compatible; future grants can explicitly include `takeoff_assist` for Pro. Trial capabilities remain replay-only and do not reset after restart/reinstall on the same Windows machine when DPAPI state is available.
- The Performance tab reports capture, encoder, buffer, queue, failure, RAM, cache, disk, and UI-latency health using one-second session samples. A unified background task controller owns migration and other disk work, with cancel/retry status feedback; notification text includes a non-colour symbol so warnings remain understandable without colour.
- Existing legacy `recording_*.mp4`/`.avi` files are copied and verified into `exports/legacy-recordings/` before originals are moved to a timestamped migration backup. The direct `MF_NATIVE` camera option uses the native CaptureHost ring when packaged and falls back to OpenCV Media Foundation for safe development/runtime compatibility.
- Portal pairing is an additive activation option: the app creates a short-lived token, six-digit fallback code, and locally rendered QR link, the signed-in website approves a selected active licence, and the app receives the existing signed authorization. New QR links open the standalone `account.tomaspisar.cz/approve/pairing` page, which shows only the current computer request, technical summary, eligible licence selector, and Approve/Decline actions. The page preserves the token through the existing email OTP login, waits for the desktop result, and shows activated, declined, failed, or expired outcomes. Opening the page records `viewed_at` in migration `0009_device_pairing_viewed.sql`; the desktop poll uses that signal to remove the QR image while approval is pending. The dashboard's manual six-digit pairing remains available. The backend persists `activating`, `declined`, and `failed` outcomes in migration `0008_device_pairing_outcomes.sql` and safely recovers stale activation claims. Email OTP remains the primary authentication flow.

- The authoritative static-site checkout now includes RelayLab at `website/tomaspisar.cz/swimming/relaylab/`. Its simplified surface keeps only the Team builder and Recommended lineup: name autocomplete, exact Czech Swimming ID/profile URL lookup, 4×25/4×50/4×100 relay settings, matching 25/50 m pool results, date filters, optional relay splits, and an exhaustive unique-swimmer lineup optimizer.
- The public Czech Swimming site rejects browser cross-origin requests, so `website/main-site-worker.ts` owns same-origin `GET /api/swimming/search` and `GET /api/swimming/swimmers/:id/times` routes. The proxy returns only RelayLab fields, validates IDs/query length, uses an eight-second upstream timeout, and applies edge caching while browser responses remain revalidatable.
- RelayLab uses a simplified light UI with restrained teal/coral accents, visible keyboard focus, 44px-class controls, responsive 375px-safe layout, and reduced-motion handling. `relaylab-core.js` is CommonJS-compatible for focused Node tests; `relaylab-core.test.cjs` covers exact filtering, relay split opt-in, unique assignments, ties, and manual completion in the core engine.
- The `/software/` catalog now lists RelayLab as `02 / WEB APP` beside LongJumpReplay, using the shared product-card layout and a link to `/swimming/relaylab/`.
- RelayLab uses one combined swimmer search field for names, exact swimmer numbers, and profile URLs. Clicking an added swimmer opens an accessible times dialog with the official Czech Swimming profile link.
- A small `Add unregistered swimmer` action opens a compact manual form for name plus four relay times. These swimmers are included in optimization and shown in the times dialog without an official-profile link.
- The distance control includes 4×25, 4×50, and 4×100. For 4×25, the 25 m pool is selected automatically and the 50 m pool option is disabled because a 25 m leg cannot be swum in a 50 m pool.
## 2026-09-13 startup splash lifecycle and visual refresh

- The Tk startup window in `app.py` must never call `root.update()` from a
  progress event after `MainWindow` has started recurring camera/UI callbacks.
  A nested update loop can continuously consume those callbacks and prevent
  `StartupWindow.destroy()` from running, leaving the topmost splash over the
  fully loaded application. Startup progress events now flush idle drawing
  only; the main window is painted, the splash is destroyed, and then the
  normal `mainloop()` begins.
- The splash uses compact custom dark rounded progress tracks and a rounded
  action style for startup failures. The Details disclosure and its persisted
  preference were removed; progress events still update only the visible
  current-stage status and real overall/current-stage values.
- Its rare startup entrance uses a visible 280 ms opacity-only strong ease-out
  fade (120 ms when Windows' client-area animation preference requests reduced
  motion); progress and layout never animate with it.
- The splash and PyInstaller bootloader continue using the existing athlete
  artwork in `assets/long_jump_splash.png`; the website's separate take-off-board
  hero remains website-only.
- Shared `themed_message()` dialogs now show semantic circular symbols for
  information, warnings, errors, and confirmation questions. Legacy info calls
  infer warning/error symbols from their title/message, while new call sites can
  use explicit warning/error helpers.

## 2026-09-13 website not-found fallback

- The static site includes a responsive bilingual `404.html` that uses the
  existing header, typography, colours, language switch, footer, and catalog
  actions. `website/wrangler.jsonc` sets Workers Assets to `404-page` handling
  so unknown public paths render this page rather than a generic response.

- Automatic take-off live gating samples the reduced board ROI at up to the UI refresh cadence, measures proximity from the nearest moving contour edge (not its centroid), and exposes `AUTO STARTING`, `AUTO READY`, `AUTO DETECTING`, calibration, and entitlement states on the live overlay. The full advisory remains conservative and never changes the official judge verdict.

- Automatic triggering anchors detailed analysis to the first near-line activity rather than the later motion peak, because the latter is commonly the shoe leaving or a following shadow. Takeoff Assist requires current-frame appearance evidence, and failed automatic analysis falls back to the trigger timestamp instead of frame zero.
- Takeoff Assist accepts a shoe entering through the top edge of a camera-cropped ROI with reduced confidence, while continuing to reject side/bottom-clipped contours; automatic analysis uses only a short post-trigger window to avoid selecting the following shadow.
