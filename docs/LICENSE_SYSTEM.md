# LongJumpReplay licensing system

Status: **the production Worker, D1 database, email activation API, customer
portal, Stripe webhook and desktop licence panel are implemented.** The
production API is live at `api.tomaspisar.cz` and the customer portal is live at
`account.tomaspisar.cz`. A separate staging D1 database and Worker
configuration are prepared; staging still needs test-mode secrets before it is
useful for a full purchase test.

## Architecture

```
Stripe Checkout
      |  checkout.session.completed, customer.subscription.*, invoice.*
      v
Cloudflare Worker  (licensing-api/)
      |
      v
Cloudflare D1      (longjumpreplay-licenses)
      |  customers / licenses / devices / verification_codes / portal_sessions
      v
LongJumpReplay
      |  email -> verification code -> device activation
      v
Signed authorization (RSA, verified offline by the app)
```

The signing key is asymmetric on purpose: the private half exists only as a
Worker secret, the public modulus is compiled into the application. A copy of
the EXE therefore cannot mint its own authorizations.

## Commercial model

| | Lifetime | Subscription |
| --- | --- | --- |
| Stripe | one-time payment | recurring subscription |
| `licenses.type` | `lifetime` | `subscription` |
| Expiry | never expires with time | active while Stripe says active |
| Devices | `MAX_DEVICES` (2) | `MAX_DEVICES` (2) |
| Offline | authorization refreshed periodically | same |

A lifetime licence is **not** a permanent offline token. The licence does not
expire, but the authorization it produces does, and gets refreshed. That is what
lets a refunded or revoked licence stop working without the app having to be
online constantly.

## Configuration

Non-secret values, in `licensing-api/wrangler.jsonc`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MAX_DEVICES` | 2 | Simultaneously activated computers per licence |
| `VERIFICATION_CODE_TTL_MINUTES` | 10 | Verification code lifetime |
| `MAX_VERIFICATION_ATTEMPTS` | 5 | Wrong-code attempts before a new code is needed |
| `OFFLINE_VERIFICATION_WINDOW_DAYS` | 30 | How long the app works between checks |
| `AUTHORIZATION_TTL_DAYS` | 30 | Signed authorization lifetime |
| `SUBSCRIPTION_GRACE_DAYS` | 7 | Grace after a subscription period ends |
| `STRIPE_PRICE_LIFETIME` | (empty) | Stripe price ID for the lifetime product |
| `STRIPE_PRICE_SUBSCRIPTION` | (empty) | Stripe price ID for the monthly product |
| `RATE_LIMIT_*` | see `src/config.ts` | Overrides; omit in production |

The public website Contact form posts to `/api/contact`. Its public Turnstile
site key is configured in `website/tomaspisar.cz/site.config.js`; the matching
private secret must be added to the Worker as `CONTACT_TURNSTILE_SECRET`.

The website reads matching values from `website/tomaspisar.cz/site.config.js`
(`licensing.deviceLimit`, `offlineGraceDays`, `updateMonths`). **These two are
not automatically linked** - changing a Worker value means changing the site
value too, or the customer-facing promise drifts from the enforcement.

### Secrets

Set with `wrangler secret put <NAME>` from `licensing-api/`. Never in
`wrangler.jsonc`, never in git, never in the EXE, never in this file.

| Secret | Purpose |
| --- | --- |
| `STRIPE_WEBHOOK_SECRET` | Verifies webhook signatures. From the Stripe webhook endpoint. |
| `STRIPE_SECRET_KEY` | Reads back line items and subscriptions. Restricted key is enough. |
| `VERIFICATION_PEPPER` | HMAC key for verification codes. Any 32 random bytes. |
| `ACTIVATION_KEY_ENCRYPTION_KEY` | Encrypts reusable portal activation keys with AES-GCM. Use a separate high-entropy secret. |
| `AUTHORIZATION_PRIVATE_KEY` | PKCS#8 RSA private key signing authorizations. |
| `MAIL_API_KEY` | Transactional email provider key. |
| `CONTACT_TURNSTILE_SECRET` | Server-side verification secret for the public contact form. |

## Database

Migrations `0001` through `0006` define the current schema. Tables:
`customers`, `licenses`, `devices`, `verification_codes`, `activation_grants`,
`stripe_events`, `rate_limits`, `events`, `portal_login_codes`, and
`portal_sessions`, `license_activation_keys`, and `device_activity`.

Notable constraints:

- `idx_customers_email` unique - email is the activation identifier.
- `idx_devices_license_machine` unique - re-activating a known machine refreshes
  it rather than consuming a second seat.
- `idx_licenses_subscription` unique - one licence per Stripe subscription, part
  of the idempotency story.
- `stripe_events` primary key - the insert failing *is* the duplicate check.

Devices use an opaque identifier derived on the customer's machine; no raw
hardware serial is sent. Activation activity stores the exact connecting IP,
Cloudflare country, app version, Windows version and architecture for account
security and support. A daily scheduled job deletes this detail after 365 days.

## API

All endpoints are POST and return JSON. Errors are `{error, message}` with a
user-safe message; internals are never returned.

### `POST /api/stripe/webhook`
Stripe only. Verifies the signature, then creates or synchronises licences.
Handled events: `checkout.session.completed`, `customer.subscription.created`,
`.updated`, `.deleted`, `.paused`, `.resumed`, `invoice.payment_succeeded`,
`invoice.payment_failed`.

### `POST /api/license/request-code`

The Worker sends the email code even when the normalized address does not yet
have an active licence. That allows the desktop flow to verify the address and
give an accurate no-licence result instead of claiming that an undelivered code
was sent. An email-only activation code is scoped separately from portal login
codes and cannot activate a device unless a licence exists when it is verified.
Verification mail includes both a styled HTML body and a plain-text fallback.
App activation uses the cyan Evidence Desk accent and an `APP ACTIVATION`
heading; portal login uses amber and `CUSTOMER PORTAL LOGIN`. The purpose also
appears in the subject line so it remains clear when HTML is unavailable.
`{email}` -> `{sent: true, expires_in_minutes}`.
Always the same response whether or not a licence exists, so the endpoint cannot
be used to discover who has bought the software.

### `POST /api/license/verify-code`
`{email, code}` -> `{verified: true, activation_grant, expires_in_seconds}`.
The grant is single-use and lives 10 minutes. A valid email-only code returns
`403 no_license` when the account still has no active licence; if checkout was
completed after requesting the code, verification uses the new licence and
returns the normal activation grant.

### `POST /api/license/activate`
`{activation_grant, machine_id, device_name?}` -> `{activated, license_type,
max_devices, authorization, expires_at}`. Returns `409 device_limit` when the
seat limit is reached.

### `POST /api/license/activate-key`
`{activation_key, machine_id, device_name?, app_version?, os_version?, architecture?}`
activates with the reusable `NNNN-LLLL-RRRR` key from the customer portal. The
endpoint is limited to 30 attempts per IP per hour. Keys are generated with Web
Crypto, stored as an HMAC verifier plus AES-GCM ciphertext, and never logged.

### `POST /api/license/verify`
`{license_id, machine_id}` -> `{valid, license_type, authorization, expires_at}`.
The periodic refresh. Returns 403 once a subscription is past its period end
plus grace.

### `POST /api/license/deactivate-device`
`{activation_grant, machine_id}` -> `{deactivated}`. Requires the same proof of
email ownership as activation, because freeing a seat is a privileged action.

### `GET /health`
Liveness only.

### Customer portal

The portal uses `https://account.tomaspisar.cz/login` for passwordless email
sign-in and `https://account.tomaspisar.cz/dashboard` for the authenticated
account. The Worker redirects the account root according to session state. It
uses a separate email verification purpose and an HttpOnly session cookie; it
never receives or stores card data.

- `POST /api/portal/request-code` - request a portal OTP for any valid email.
- `POST /api/portal/verify-code` - exchange the OTP for a portal session.
- `GET /api/portal/account` - licence, device, invoice and billing status.
- `POST /api/portal/billing` - create a Stripe Customer Portal session.
- `POST /api/portal/deactivate-device` - free one device slot.
- `POST /api/portal/delete-device` - delete an already-deactivated device and
  its detailed activity history.
- `GET /api/portal/device-details?device_id=...` - owner-only technical and
  one-year activity detail.
- `POST /api/portal/activation-key/ensure`, `/reveal`, `/regenerate` - create,
  reveal, or rotate the one reusable key for an active licence. Rotation
  disconnects key-activated devices only; email-activated devices stay active.
- `POST /api/portal/logout` - revoke the current portal session.

Portal access proves control of an email address and does not require a
purchase. An account without a licence receives an empty account view with a
link to buy LongJumpReplay. A later Stripe purchase made with the same
normalised email is attached to that existing account automatically. Portal
codes are stored separately from activation codes and cannot activate the
desktop application.

An additive portal pairing path is now available alongside email OTP and the
reusable key: the desktop shows a short-lived six-digit code and a portal link,
the signed-in owner approves that exact computer and licence, and the code is
consumed when the desktop receives its existing signed authorization. The
portal still uses email OTP; pairing is not a replacement authentication flow.
Passkeys are a useful future portal-login upgrade. Floating network licences,
shared permanent club passwords and hardware dongles are intentionally not
planned because they add support burden or weaken ownership controls.

Both the activation flow and the portal use ten-minute email codes. A customer
can activate up to two computers. Authorizations are signed for 30 days and
the desktop app checks them online at every frozen-app startup and refreshes the
authorization when successful. A still-valid signed authorization preserves
offline use during temporary connectivity or server failures. Explicit licence
or device rejection blocks startup and requires activation. Lifetime entitlement
never expires, while a subscription receives seven days of grace after its paid
period before verification stops.

## Authorization token

`LJRA1.<base64url payload>.<base64url signature>`, RSASSA-PKCS1-v1_5 / SHA-256.
Payload: `product`, `version`, `license_id`, `license_type`, `machine_id`,
`max_devices`, `issued_at`, `expires_at`.

Verified by `src/authorization.py` with no network access and no new
dependencies, reusing `_rsa_verify_with_key` from `src/licensing.py`.

Cross-language compatibility was verified by signing with the Worker's real
code under Node and verifying in Python: signature valid, canonical JSON
identical byte for byte including non-ASCII, tampered payload rejected, wrong
key rejected.

## Offline behaviour

1. Activation requires internet, once.
2. The app then verifies the stored authorization locally at every start.
3. `should_refresh()` triggers a refresh once past the halfway point of the
   authorization's life, so a laptop online at the club renews quietly rather
   than discovering it needs a connection at the track.
4. If the authorization expires, the app must ask for a connection - it must not
   silently fail, and it must never discard competition data.

A failed subscription payment does not disable anything immediately:
`past_due` still counts as active, and the licence only stops verifying once
`current_period_end + SUBSCRIPTION_GRACE_DAYS` has passed.

## Local development and testing

```powershell
cd licensing-api
npm install
node scripts/generate-signing-key.mjs > key.txt   # gitignored
node scripts/make-dev-vars.mjs key.txt            # writes .dev.vars, gitignored
npx wrangler d1 migrations apply longjumpreplay-licenses --local
npx wrangler dev --local --port 8787
node scripts/e2e.mjs http://127.0.0.1:8787
```

`scripts/e2e.mjs` covers webhook forgery, replay and tampering; lifetime and
subscription purchase; duplicate webhook delivery; the full email-code
activation; the device limit and freeing a slot; subscription cancellation; and
input validation. It recovers the verification code by brute-forcing the HMAC
against the local pepper rather than adding any test backdoor to the Worker.

Python side: `.venv\Scripts\python.exe -m pytest tests/test_authorization.py`.

## Deployment

The production deployment has been run and verified. The staging deployment
is configured but intentionally has no credentials or live price IDs yet.

1. ~~Create the database~~ **Done.** `longjumpreplay-licenses`,
   `afd54a54-bccb-494c-ac6d-377b00652c40`, primary region WEUR, already wired
   into both `d1_databases` blocks in `wrangler.jsonc`.
2. ~~Apply the schema~~ **Done.** All 8 tables and 11 indexes exist on the
   remote database, which is empty. The unique constraints on
   `customers.email`, `devices(license_id, machine_id)` and the
   `stripe_events` primary key were each confirmed to reject a duplicate, and
   the `licenses.type` CHECK to reject an unknown type.

   Note that the default local environment uses local SQLite when launched
   with `wrangler dev --local`. Staging has its own D1 database:
   `longjumpreplay-licenses-staging` (`6e80c8e7-b1da-4f60-9f76-bb3a0505d748`).
3. Production uses the existing verified signing key and the five production
   secrets. Secret values are intentionally not documented or exposed here.
4. Production price IDs are the live lifetime and monthly prices in
   `wrangler.jsonc`; the live Stripe webhook is
   `https://api.tomaspisar.cz/api/stripe/webhook`.
5. Production was deployed with the API route and the account portal route.
   `/health`, webhook signature rejection, CORS, unauthenticated portal access,
   and static portal delivery were checked after deployment.
6. For a safe purchase rehearsal, create separate Stripe test-mode prices,
   webhook secret, restricted test key, and Resend test sending key, then set
   the staging secrets and deploy with `npx wrangler deploy --env staging`.
   Never point test webhooks at the production database.

## Operations

**Revoke a licence**
```sql
UPDATE licenses SET status = 'suspended', updated_at = unixepoch() WHERE id = ?;
```
Takes effect at the next verification, so within `AUTHORIZATION_TTL_DAYS`.

**Free a device slot for a customer**
```sql
UPDATE devices SET status = 'deactivated', deactivated_at = unixepoch()
 WHERE license_id = ? AND machine_id = ?;
```

**See what happened to an order**
```sql
SELECT type, detail, created_at FROM events WHERE license_id = ? ORDER BY created_at;
```

**A purchase produced no licence** - look for `license_creation_failed` in
`events`. The usual cause is a Stripe price ID that is not mapped in
`STRIPE_PRICE_LIFETIME` / `STRIPE_PRICE_SUBSCRIPTION`; the Worker refuses to
guess a licence type rather than issue the wrong one.

## Privacy

Stored: email address, Stripe customer/subscription IDs, an opaque per-device
identifier, activation and verification timestamps, and an event log. Not
stored: card details, verification codes (only an HMAC), hardware serials,
computer names, locations, or anything about competitions and athletes.

`website/tomaspisar.cz/privacy/index.html` describes this. It was updated when
the site copy changed and should be re-read once the system is actually live.

## Remaining release gates

- A real Stripe purchase has not been run in this session because the agreed
  validation path is a separate test-mode setup, not a live charge. Staging
  needs test-mode Stripe prices, webhook secret, restricted test key, Resend
  test sending key, pepper and signing key before that rehearsal can run.
- The desktop 3.3.0 release is built as an Inno Setup installer and verified
  by source, GUI, frozen, clean-install and in-place-upgrade tests. Publication
  uses the signed R2 channel documented in `docs/RELEASING.md`.
- The website still needs publishable Terms, seller identity, withdrawal and
  refund information. Those facts must come from the seller; they must not be
  invented in source code. The privacy page also deserves a final legal review.
- `license_service/` is the older machine-code/key design. It remains for
  legacy compatibility but is not part of the new customer purchase flow.

### Lifetime additional computers

Active lifetime customers can purchase one-time marginal computer add-ons from the authenticated portal. The existing licence row is extended from its current limit; subscription and inactive licences are ineligible, and the hard lifetime maximum is 10 computers.

The Worker calculates these CZK prices server-side: computer 3 is 1,490 Kč, computer 4 is 1,290 Kč, and computers 5 through 10 are 990 Kč each. Checkout uses Stripe-hosted Checkout with one inline `price_data` line item per marginal computer, so stepped totals are exact without trusting browser prices. Metadata includes `customer_id`, `license_id`, `quantity`, `product`, and `purchase_type=additional_computers`.

Migration `0005_additional_computers.sql` records each paid Checkout Session once. Signed `checkout.session.completed` and `checkout.session.async_payment_succeeded` events only fulfill when Stripe reports `payment_status=paid`; a conditional D1 update prevents concurrent sessions from exceeding 10, and the resulting `additional_computers_purchased` event records amount, currency, Stripe IDs, quantity, and resulting limit. The portal hides the offer at 10 computers.

The local migration and Worker test suite are safe to run before deployment. Do not apply the migration remotely or add production Stripe configuration until the isolated Stripe test-mode rehearsal has passed.
