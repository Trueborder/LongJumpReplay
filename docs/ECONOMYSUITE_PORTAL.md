# EconomySuite / Pantheon account portal

## Routes and ownership

`https://account.tomaspisar.cz/login?product=economysuite` selects player login. The product chooser also links to LongJumpReplay. Email/password, OTP recovery and session cookies are shared; player setup needs a password, while LongJumpReplay keeps its required real-name profile. Existing `/dashboard/*` remains the LongJumpReplay dashboard.

The player dashboard has `/economysuite/overview`, `/statistics`, `/progress`, `/appearance`, `/store`, `/purchases`, `/settings` and `/pair`. Prefix each suffix with `/economysuite`. Store and pairing shells are public; private data and every player mutation require a session, and mutations require the existing origin/CSRF checks. Pairing tokens arrive in URL fragments, are stored briefly in session storage, and are stripped from the URL.

Worker logic is `licensing-api/src/economysuite.ts`; account assets are `website/tomaspisar.cz/account/economysuite`. Shared login JavaScript is under `website/tomaspisar.cz/assets/js/account`, so deploy the main-site Worker as well as the account/API Worker when it changes.

`ECONOMYSUITE_DB` is separate from licensing D1:

| Environment | Database | ID |
| --- | --- | --- |
| Production | economysuite-player-portal | b0e45bf6-0490-4d6d-9bfa-50d15355c44f |
| Staging | economysuite-player-portal-staging | 6c571619-685a-4cde-a302-10f88fa20151 |

Migrations live in `licensing-api/economysuite-migrations`. UUID/account uniqueness is enforced by D1. Snapshots contain allowlisted gameplay fields. Rankings require opt-in and return only player identity and one selected metric.

## Secrets and deployment

Set secrets independently for each environment with Wrangler:

- `ECONOMYSUITE_BRIDGE_SECRET`: shared only with the Pantheon plugin. Signed requests contain a timestamp, UUID nonce and HMAC-SHA256 over `timestamp\nnonce\npathname\nraw-body`. The Worker accepts two minutes of clock skew and rejects nonce reuse.
- `ECONOMYSUITE_WEBHOOK_SECRET`: signing secret for the dedicated EconomySuite Stripe webhook.
- `ECONOMYSUITE_STRIPE_KEY`: restricted key for the EconomySuite Stripe environment. It needs product/price reads, Checkout Session create/read, PaymentIntent/charge reads, and dispute reads. The production implementation currently falls back to the existing `STRIPE_SECRET_KEY` if an EconomySuite key is absent. Staging has its own isolated sandbox key and cannot use live billing data.
- `ECONOMYSUITE_PURCHASES_ENABLED`: non-secret kill switch in Wrangler vars. Leave `false` until catalog, sandbox rehearsal, and Paper runtime verification are complete. It stops new checkouts while allowing signed deliveries/refunds to finish.

Local `secret-economysuite-*.txt`, `secret-economysuite-stripe.toml`, `.wrangler/` and the plugin's `website-bridge.secret` are ignored. They contain credentials and must stay local. Grant host file access only to the server operator.

From `licensing-api`:

```powershell
npm.cmd run typecheck
npm.cmd test
npx.cmd wrangler d1 migrations apply ECONOMYSUITE_DB --remote --env production
npx.cmd wrangler deploy --env production
```

From `website`, use `../licensing-api/node_modules/.bin/wrangler.cmd deploy --config wrangler.jsonc` for the public site's sibling login assets. For staging, apply both `DB` and `ECONOMYSUITE_DB` migrations and deploy with `--env staging`. Keep the two Stripe environments and bridge secrets separate.

## Stripe-managed catalog

The store reads active Stripe Products with expanded default Prices, only publishing explicitly opted-in Pantheon packages. No quantities, descriptions or prices are hardcoded in the storefront.

| Location | Metadata / property | Value |
| --- | --- | --- |
| Product metadata | es_product | economysuite |
| Product metadata | es_server | pantheon |
| Product metadata | es_published | true to show it; false while drafting |
| Product metadata | es_sort | Optional nonnegative integer |
| Product | active / default_price | Active product with its selected active Price |
| Default Price | currency / type | czk / one_time |
| Price metadata | es_currency | coins or tokens |
| Price metadata | es_amount | Positive integer, at most 1,000,000,000 |

The backend re-fetches this catalog before creating a checkout. It snapshots the chosen UUID, quantity and CZK price in the order. Stripe Checkout uses one item, quantity one, no client-defined amounts or discounts, and dynamic payment methods. Fulfillment validates the session's metadata, price and paid total; the success page never credits currency.

`scripts/seed-economysuite-catalog.mjs` requires `ECONOMYSUITE_STRIPE_TEST_KEY` and refuses live keys. It seeds six unpublished fixtures: 1,000/5,000/10,000 coins and 10/50/100 tokens. Their 100 CZK test price is a fixture, not a proposed live price. Live package quantities and prices remain an operator decision in Stripe.

## Dedicated webhooks and durable delivery

The production endpoint is `https://account.tomaspisar.cz/api/economysuite/stripe/webhook`, Stripe ID `we_1UNHvtRzuUbjN0GO8Ob7Hutj`. The existing LongJumpReplay endpoint is unchanged and explicitly ignores `economysuite_currency` checkout events. EconomySuite ignores unrelated product events and never creates licences.

Subscribe to completed/async-succeeded/async-failed/expired Checkout Sessions, charge refunds, refund updates/failures, and dispute created/updated/closed/funds-withdrawn/funds-reinstated. Signed handlers retrieve current Stripe payment/refund/dispute state rather than trusting event arrival order. Optimistic order revisions and a D1 transaction atomically record the event, cumulative target and queued operation. Transient failures receive a retry response.

The plugin applies cumulative target revisions in SQLite transactions, records operation IDs, and acknowledges only after commit. Offline players are supported; stopped servers retain queued operations. Refund shortfalls become per-currency debt, with spending/transfer guards in the authoritative plugin database. Pairing/unlinking cannot redirect an existing purchase to another UUID.

## Sandbox and validation

The isolated claimable sandbox is `acct_1UNHD7RZVoxIJv8F`, created by the Stripe CLI proof-of-work flow on 2026-10-05 for `info@tomaspisar.cz`. Claim it before 2026-10-12; its claim URL is in the ignored local Stripe TOML. Review/rotate its test credentials when claiming it. No live packages were created.

`scripts/rehearse-economysuite.mjs` uses only the named staging databases and refuses live Stripe keys. It creates a temporary test account, performs both pairing confirmations, temporarily publishes one sandbox package, creates/pays an actual sandbox Checkout Session using Stripe's test token, delivers signed events, tests partial/full refunds, then removes its D1 fixtures and returns the product to unpublished. The payment-page steps follow the [official Stripe CLI fixture](https://github.com/stripe/stripe-cli/blob/master/pkg/fixtures/triggers/checkout.session.completed.json).

Run with staging purchases temporarily enabled, then restore the configured kill switch:

```powershell
npx.cmd wrangler deploy --env staging --var ECONOMYSUITE_PURCHASES_ENABLED:true
# Requires the Stripe CLI on PATH, or STRIPE_CLI_BIN pointing to its executable.
node scripts/rehearse-economysuite.mjs
npx.cmd wrangler deploy --env staging
```

Worker tests exercise real local D1, registration without a player real-name profile, the unchanged LongJumpReplay setup gate, ownership/CSRF, two-step pairing, replay rejection, privacy filtering, payment signatures, duplicate events, refunds and disputes. Plugin database tests cover retry/old-revision behavior, rollback, cosmetic ownership, immediate paid tokens and debt settlement. See `C:/Users/xpisa/PROJECTS/EconomySuite/WEBSITE_PORTAL.md` for the remaining Paper runtime checks.

The full plugin suite has four existing failures, reproduced in a detached original checkout: two OrdersDatabaseTest registry initialization failures, one active-token expectation and one tournament-config expectation. The website suite also has an existing stale contact test expecting a direct email link removed in the original source. These are distinct from the passing portal tests. No browser surface is connected in this session, so authenticated visual/mobile verification remains required.

Verified on 2026-10-05: 39 Worker tests and typecheck passed; the real staging sandbox rehearsal passed pairing, paid Checkout, signed duplicate webhook delivery, and partial/full refunds. Fixtures were removed and all six products restored to unpublished. Both staging and production purchase switches are off. Plugin portal database tests pass; actual Paper and authenticated browser checks remain pending.

The EconomySuite API uses Stripe 2026-09-30.endive. The live webhook was created with 2026-08-26.dahlia event payloads; handlers validate/retrieve objects through the current API. Latest-order checkout mapping is recoverable after interruptions, and already-disputed charges are reconciled even if the dispute event arrived before the checkout event.
