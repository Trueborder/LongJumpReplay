# EconomySuite 2.41.0 supporter rank store

## Products and behavior

Three one-time CZK products: VIP 39 Kč, VIP+ 69 Kč, MVP 99 Kč, each 604800 seconds. Time starts at Stripe's verified charge time, not bridge delivery or first login. A higher tier pauses remaining lower-tier time; renewals add a week. No subscription, gifting, transfer to another UUID, personal economic multiplier or automatic OP entitlement is introduced.

The existing store, consent evidence, confirmation email, purchase history, signed bridge and refund path are reused. `product_type=rank`, `rank_id`, `rank_paid_at` and `currency_type=rank` distinguish rank time from real coin/token credits; `currency_amount` and `target_amount` hold seconds for this product kind only. Currency fulfillment is never called for a rank order. Existing currency orders retain their shape and values.

Rank cosmetic settings and the authoritative grant timeline belong to EconomySuite. The portal displays its synchronized active rank, expiration, paused time and chosen profile frame. Offline/delayed snapshots remain snapshots, not a second source of entitlement truth. The checkout confirmation explains offline expiry, paused lower tiers and seven-day duration.

## Activation checklist

1. Back up the separate EconomySuite D1 database. Apply `licensing-api/economysuite-migrations/0007_supporter_ranks.sql` through its normal migration path as one transaction. It rebuilds the order CHECK constraint without changing IDs, preserves purchase evidence, checks foreign keys and adds `bridge_status.ranks_version`. Do not apply it statement-by-statement to a live database.
2. Deploy the compatible backend/assets with rank sales still disabled. Install EconomySuite 2.41.0 on staging and verify its signed poll advertises `ranks_version: 1`. Older versions cannot receive rank operations; rank checkout also requires a compatible reported version.
3. In an isolated Stripe sandbox, optionally run `node scripts/seed-economysuite-ranks.mjs` from licensing-api with `ECONOMYSUITE_STRIPE_TEST_KEY` supplied through the environment. The script refuses live keys and creates **unpublished** products only. Never put credentials in code, arguments printed to logs or documentation.
4. Required product metadata: `es_product=economysuite`, `es_server=pantheon`, `es_kind=rank`, `es_rank=vip|vipplus|mvp`, `es_published=true` only after review. Its active default price must be one-time CZK, respectively 3900/6900/9900 minor units, with price metadata `es_duration_seconds=604800`. Currency product metadata remains unchanged.
5. For staging only, enable `ECONOMYSUITE_RANKS_ENABLED=true` alongside the existing purchases flag. Perform actual sandbox payment, asynchronous completion, duplicate webhook, refund, dispute recovery and offline-delivery tests. Confirm consent and email wording for temporary ranks with the operator before live publication. Do not assume mocked fulfillment proves real Stripe delivery.
6. Validate on Paper 1.21.11: cosmetics, rank expiry and paused time, lobby restrictions, duels, spectator, invisibility, reload and 30-player visuals. Configure explicit lobby regions; defaults grant no portable utility access.
7. Only after review publish equivalent live products, apply the reviewed migration/deployments, install the JAR and enable the ranks flag. This implementation did not perform live publication, production migration, deployment or server restart.

The new flag is optional and defaults to off when absent. Enabling the existing currency store alone never exposes rank checkout. Prices in the plugin are informational; changing the approved rank prices requires matching backend catalog validation and portal comparison copy, not just editing ranks.yml.

## Delivery and refunds

Only a signature-verified webhook reconciled against the server's stored order, exact price, amount, customer and UUID can enqueue `rank_purchase`. Browser success pages do not grant time. Both normal and asynchronous successful Checkout events are handled. Idempotent order revisions and immutable original payment time survive duplicate/out-of-order delivery.

The operation contains `order_id`, `rank`, `paid_at` and `effective_at` in milliseconds, `duration_seconds`, and `revision`. Full grants are 604800 seconds; cumulative refunds proportionally reduce that budget. Open disputes remove the remaining affected time; a won dispute restores unused entitlement, not already consumed time. Other purchases and users' rewards from a previously activated shared booster are not clawed back. Existing currency refund/debt handling is unchanged.

Compatibility is advertised in the existing signed poll. Unknown old plugins retain pending rank operations instead of receiving an unsupported operation. The plugin journals grants before acknowledging; a crash between the journal and ack is safe to retry.

## Local validation and remaining boundaries

- Worker suite: 74 passing tests at implementation validation, including rank metadata, payment-time units, duplicate rank events, partial refunds, old-plugin gating, retired-title rejection and populated migration rehearsal with foreign-key checks.
- Website suite includes four cosmetic selections without titles, request snapshot safety, rank copy and the preserved portal motion behavior.
- No real Stripe sandbox purchase was submitted: the connected Stripe app required reauthentication. No secrets were read or changed.
- No live Paper/client visual test, load test, production purchase, migration or deployment is claimed.

Primary references used for the implementation: [Stripe fulfillment](https://docs.stripe.com/checkout/fulfillment), [webhook signature verification](https://docs.stripe.com/events/manage-webhook-endpoints), [D1 deferred foreign keys](https://developers.cloudflare.com/d1/sql-api/foreign-keys/).
