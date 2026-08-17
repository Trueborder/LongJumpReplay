# LongJumpReplay licensing system

Status: **the Worker, database, API and client verifier are built and tested
locally. Nothing is deployed, and the desktop activation UI is not yet wired
up.** See "What is not done" at the end before relying on any of this.

## Architecture

```
Stripe Checkout
      |  checkout.session.completed, customer.subscription.*, invoice.*
      v
Cloudflare Worker  (licensing-api/)
      |
      v
Cloudflare D1      (longjumpreplay-licenses)
      |  customers / licenses / devices / verification_codes / events
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
| `AUTHORIZATION_PRIVATE_KEY` | PKCS#8 RSA private key signing authorizations. |
| `MAIL_API_KEY` | Transactional email provider key. |

## Database

`licensing-api/migrations/0001_init.sql`. Tables: `customers`, `licenses`,
`devices`, `verification_codes`, `activation_grants`, `stripe_events`,
`rate_limits`, `events`.

Notable constraints:

- `idx_customers_email` unique - email is the activation identifier.
- `idx_devices_license_machine` unique - re-activating a known machine refreshes
  it rather than consuming a second seat.
- `idx_licenses_subscription` unique - one licence per Stripe subscription, part
  of the idempotency story.
- `stripe_events` primary key - the insert failing *is* the duplicate check.

Only the email address is personal data. Devices are stored as an opaque
identifier derived on the customer's machine; no hardware serials, computer
names or locations are stored.

## API

All endpoints are POST and return JSON. Errors are `{error, message}` with a
user-safe message; internals are never returned.

### `POST /api/stripe/webhook`
Stripe only. Verifies the signature, then creates or synchronises licences.
Handled events: `checkout.session.completed`, `customer.subscription.created`,
`.updated`, `.deleted`, `.paused`, `.resumed`, `invoice.payment_succeeded`,
`invoice.payment_failed`.

### `POST /api/license/request-code`
`{email}` -> `{sent: true, expires_in_minutes}`.
Always the same response whether or not a licence exists, so the endpoint cannot
be used to discover who has bought the software.

### `POST /api/license/verify-code`
`{email, code}` -> `{verified: true, activation_grant, expires_in_seconds}`.
The grant is single-use and lives 10 minutes.

### `POST /api/license/activate`
`{activation_grant, machine_id, device_name?}` -> `{activated, license_type,
max_devices, authorization, expires_at}`. Returns `409 device_limit` when the
seat limit is reached.

### `POST /api/license/verify`
`{license_id, machine_id}` -> `{valid, license_type, authorization, expires_at}`.
The periodic refresh. Returns 403 once a subscription is past its period end
plus grace.

### `POST /api/license/deactivate-device`
`{activation_grant, machine_id}` -> `{deactivated}`. Requires the same proof of
email ownership as activation, because freeing a seat is a privileged action.

### `GET /health`
Liveness only.

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

Nothing below has been run - it all needs Cloudflare and Stripe credentials.

1. ~~Create the database~~ **Done.** `longjumpreplay-licenses`,
   `afd54a54-bccb-494c-ac6d-377b00652c40`, primary region WEUR, already wired
   into both `d1_databases` blocks in `wrangler.jsonc`.
2. ~~Apply the schema~~ **Done.** All 8 tables and 11 indexes exist on the
   remote database, which is empty. The unique constraints on
   `customers.email`, `devices(license_id, machine_id)` and the
   `stripe_events` primary key were each confirmed to reject a duplicate, and
   the `licenses.type` CHECK to reject an unknown type.

   Note that `wrangler.jsonc` points the default and production environments at
   the same database. Local work uses `wrangler dev --local`, which has its own
   SQLite file and never touches this one, but `wrangler dev` **without**
   `--local` would read and write production data. Create a second D1 database
   for a staging environment if that becomes a risk.
3. `node scripts/generate-signing-key.mjs` and set the private half:
   `npx wrangler secret put AUTHORIZATION_PRIVATE_KEY`
   Put the printed public modulus into `AUTHORIZATION_PUBLIC_KEY_N` in
   `src/authorization.py` and ship a build containing it.
4. Set the other secrets: `STRIPE_WEBHOOK_SECRET`, `STRIPE_SECRET_KEY`,
   `VERIFICATION_PEPPER`, `MAIL_API_KEY`.
5. Fill `STRIPE_PRICE_LIFETIME` and `STRIPE_PRICE_SUBSCRIPTION`.
6. `npx wrangler deploy --env production`
7. Point a Stripe webhook at `https://api.tomaspisar.cz/api/stripe/webhook`.
8. Test in Stripe **test mode** before switching live keys.

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

## What is not done

- **The Worker is not deployed.** The D1 database exists and the price IDs are
  set, but nothing is running at `api.tomaspisar.cz`. DNS for that hostname
  already resolves to Cloudflare, so only the Worker and its route are missing.
- **No secrets are set.** All five are still absent, so even once deployed the
  Worker would reject webhooks and could not sign or send anything.
- **No Stripe webhook exists**, so a purchase creates no licence.
- **No email provider**, so no verification code can be delivered.
- **The desktop activation UI is not wired up.** `src/authorization.py` verifies
  authorizations, but `src/licensing.py`'s dialog still asks for an `LJR2` key
  and there is no code that calls the API. Until that is built, a customer
  cannot actually activate through this system.
- **`AUTHORIZATION_PUBLIC_KEY_N` is `None`**, so the client fails closed.
- **`license_service/`** is the older design (machine code at checkout, key
  emailed by hand). It is superseded by this system but has not been removed,
  because it is what would issue a licence today.
- **No Terms of Service or refund policy** on the website, while live payments
  are being taken.
