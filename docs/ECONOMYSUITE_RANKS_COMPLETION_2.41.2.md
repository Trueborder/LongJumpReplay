# Rank completion — 2026-10-18

> **Production status update:** The operator subsequently waived sandbox payment tests. Production migrations, web/backend, the Exaroton 2.41.2 JAR and live rank catalog are now deployed; compatible signed polling was verified before opening sales. See [the production record](ECONOMYSUITE_RANKS_PRODUCTION_2026-10-18.md). The blocker section below records the earlier state, not the current deployment. Payment/refund and client visual tests remain unperformed.

## Implemented and checked

- EconomySuite 2.41.2 fixes the Bukkit descriptor gate preventing ordinary rank holders from reaching `/craft` and `/ec`. The executor still checks authenticated state, active rank and explicit WorldGuard lobby allowlists; staff permissions are not granted to rank holders.
- Rank container click/drag checks enforce expiry immediately. Glow and portable containers have independent cleanup ownership. The master switch disables limits/badges/activation without deleting paid grants or restarting a booster's original clock.
- Preset version 2 stores cosmetic category switches and own-pet/emote/badge preferences. Restore revalidates every cosmetic against current access; pre-versioned presets remain readable. Financial revisions cannot silently change meaning when replayed with the same revision number.
- The portal marks an expired saved rank as awaiting synchronization instead of showing it and its frame as active. Delivery payloads reject unsafe/fractional/nonfinite timestamps and revisions. Prices and weekly durations are unchanged.

## Actual Cloudflare staging work

On 2026-10-18, the existing isolated `economysuite-player-portal-staging` database was upgraded through migrations 0007 and 0008 (including its pending prerequisite migrations). `PRAGMA foreign_key_check` returned no rows. No production data was copied into staging.

The staging Worker was built with `wrangler deploy --dry-run --env staging`, then deployed as version **63274c7b-cbe5-45d0-a13d-1b23d55f229d** on `api-staging.tomaspisar.cz/*`. Its bindings point to staging databases. Purchase/game flags remain false and no rank-sales flag was enabled. Health returns 200, anonymous account requests return 401 and unsigned bridge requests return 403. These smoke checks do not prove a real payment or authenticated gameplay flow.

## What still blocks live launch

The Stripe connector initially required reauthentication. After the operator reconnected it on 2026-10-18, it exposed only the live Tomas Pisar account (`livemode: true`), not a sandbox. A read-only audit found eight existing Pantheon currency products and no rank products. No products were created/published and no payment/refund was executed. The operator was asked to add the intended sandbox through Stripe's account-access management. No key was requested or exposed. Finish the real sandbox payment/refund checklist before enabling sales.

Production read-only checks confirmed migrations **0007_supporter_ranks.sql** and **0008_web_daily_rewards.sql** remain pending. The production bridge schema therefore cannot yet report `ranks_version`. No production migration, website/Worker deployment, server restart or plugin installation was performed in this completion pass. The staging deployment is not the player account production site.

After adding sandbox access: run the real sandbox checkout/refund and delayed delivery checks; perform the Paper/client staging checklist; back up production data; apply the reviewed migrations; deploy compatible backend/assets; install the new JAR and configure lobby region IDs; verify a fresh signed poll; only then publish approved live rank products and enable the rank-sales flag. Keep purchases single-payment, seven-day CZK products at 39/69/99 Kč. Never substitute a locally fabricated webhook for an actual Stripe sandbox verification.

For plugin test counts and the JAR, see `docs/RANK_COMPLETION_2.41.2.md` in the EconomySuite repository. Existing rank documentation remains the full operator checklist.
