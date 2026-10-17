# EconomySuite 2.41.1 — daily website reward

## Player behavior

- The existing store and account overview show **Daily website reward** in Czech/English, even before the first gameplay snapshot arrives. Anonymous users see sign-in; unpaired accounts see pairing instead of a claim button.
- A verified linked player can claim a uniformly random integer **1–5 tokens**, once per calendar day in **Europe/Prague**. No purchase or rank is required. This is not the in-game `/daily` reward and shared daily-coin boosters do not multiply it.
- The claim is fixed before delivery; refreshes, concurrent tabs, repeated clicks, response loss and account relinking cannot reroll it. The UI distinguishes available, queued, credited and failed delivery. Queued rewards persist over midnight and server downtime.
- Existing token-unlock requirements apply. An ineligible player's tokens enter the existing pending balance and unlock through the normal gameplay path; the website does not bypass eligibility or refund-debt settlement.
- No random amount is advertised as credited before the server acknowledges. Balances remain the plugin's synchronized source of truth.

## Activation

1. Back up the database and plugin data. Apply all existing migrations in order, then `0008_web_daily_rewards.sql` to the EconomySuite D1 binding. This migration only adds the daily-claim table and protocol capability column.
2. Deploy the tested backend and account assets together using the existing production process. This change does not publish Stripe products or enable rank sales.
3. Install the single `EconomySuite-2.41.1.jar` while the server is stopped, preserving configuration and player data. The bridge must already be configured. A server restart/production installation has not been performed as part of local implementation.
4. Confirm the plugin advertises `web_daily_version: 1`. Old plugins cannot consume the new operation, and claims remain queued until upgraded. Do not clear queued operations to resolve an upgrade delay.
5. Test one real linked player's claim, retry, inventory-independent token credit, offline queue and next-day availability. Confirm the short in-game checklist row and cycling bossbar. The web portion opens the account store; the game portion runs `/daily`.

## Operational contract

`POST /api/economysuite/daily/claim` accepts no client-selected amount, UUID or date. `GET /api/economysuite/account` supplies `daily_reward` with amount/status, day and next reset epoch. The signed poll exports current-day claim states and gates `web_daily` operations by protocol version. The plugin validates a stable `web-daily:<uuid>:<YYYY-MM-DD>` claim ID and amount limits, and atomically records both the wallet change and delivery. Historical claims stay separate from purchased order records.

Failed delivery does not unlock another roll; investigate the operation and plugin logs, then retry that same claim through the existing operational recovery process. Never manually credit a replacement and subsequently replay the original operation.

Local validation covers authentication/CSRF, concurrent claims, relinking, retry/ack behavior, protocol gating, Prague midnight/DST, plugin persistence and pending-token behavior, and browser-script double-click protection. See the plugin's `docs/WEB_DAILY_2.41.1.md` for release test counts. No production migration/deployment, server restart or live Paper/client verification is claimed.

Reference: the claim/outbox uses [D1 transactional batch semantics](https://developers.cloudflare.com/d1/worker-api/d1-database/#batch).
