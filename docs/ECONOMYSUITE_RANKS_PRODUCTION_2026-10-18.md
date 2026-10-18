# EconomySuite ranks — production deployment, 2026-10-18

## Authorization and limits

The operator explicitly authorized production deployment without Stripe sandbox testing, then confirmed backing up and replacing EconomySuite 2.40.1 with 2.41.2 on Exaroton and starting the offline server. No payment, checkout order, refund, fabricated payment webhook or test entitlement was executed. This record supersedes the earlier sandbox-access blocker in the completion report.

## Completed production work

- Exported the EconomySuite D1 database before migration. The private backup is outside the repository in `C:/Users/xpisa/Documents/Codex/Pantheon-rank-deployment-backup-2026-10-18/economysuite-pre-ranks.sql`; SHA-256 `71AD17223193BD5D6A274DC007BE352F774250995B36C6415B78CC1164B2A4FE`.
- Applied only the EconomySuite migrations 0007 and 0008. Before/after counts remained: 21 store orders, 19 purchase consents, 87 bridge operations and 8 player links. `PRAGMA foreign_key_check` returned no rows. No pending EconomySuite migrations remain. The separate LongJumpReplay license database was not migrated.
- Deployed backend and account assets first with rank sales disabled (Worker version `0c159580-0b99-40e4-a8b1-6e25e4d8a5ac`). After the compatible signed poll, published the three approved rank products and enabled `ECONOMYSUITE_RANKS_ENABLED=true` only for production. Final Worker version: `e7b6781d-8c96-459f-b3bd-358237ff344b` (`longjumpreplay-licensing-production`). Existing secrets and currency products were not changed.
- Backed up the actual old JAR and data folder, including `economy.db`, before the first new-version start. Files are in the same private backup folder. Old JAR SHA-256: `914475E0E483DAB9050E5613C487BF54521E51C70DA35C3C1835A57E988A87AD`; data ZIP SHA-256: `D5EFD0CD4194EC61BDF2105BE6FB58E9A4C51C5708BF6F3B76746D48595F0CFB`.
- Uploaded the release JAR, removed only the backed-up `plugins/EconomySuite-2.40.1.jar`, and preserved the entire plugin data folder. The installed JAR is EconomySuite 2.41.2, SHA-256 `17052E0367A263909D1DB85026696AFDF14F94C9CE3E873D0DE2A2F311B98249`.
- Actual Paper 1.21.11 startup log confirms EconomySuite 2.41.2 enabled, spawn integration active (22 holograms, 5 leaderboards), duel lobby active, and server `Done (36.058s)` at 08:36:54 Europe/Prague. Authenticated bridge polling reported `ranks_version=1` and `web_daily_version=1` before publication. This verifies startup/protocol compatibility, not payment delivery or client visuals.
- Configured `plugins/EconomySuite/ranks.yml` to allow lobby utilities only in the verified WorldGuard `spawn` region in world `spawn` and `lobby` region in world `lobby`. No WorldGuard files or flags were changed; whole-world permissions remain off. Existing arena and spawn-parkour exclusions remain in plugin code.
- A second startup with the final allowlist completed at 08:42:12, and console `economysuite:rankadmin reload` returned `Ranky a boostery načteny.` at 08:42:56. Exaroton showed online / 20 TPS / zero players. Its existing idle-stop countdown is unchanged; an empty server may stop automatically. The startup screenshot is saved with the private backups as `server-online.jpg`.

## Published Stripe catalog

All are active, published, CZK, one-time, with price metadata `es_duration_seconds=604800` and product metadata scoped to EconomySuite/Pantheon.

| Rank | Seven-day price | Product ID | Default price ID |
|---|---:|---|---|
| VIP | 39 Kč | `pantheon_rank_vip_7days` | `price_1URnZmRzuUbjN0GOeJUWb1Fo` |
| VIP+ | 69 Kč | `pantheon_rank_vipplus_7days` | `price_1URnZpRzuUbjN0GOzFZm2Owq` |
| MVP | 99 Kč | `pantheon_rank_mvp_7days` | `price_1URnZtRzuUbjN0GO2iKBUtYI` |

Existing webhook `we_1UNHvtRzuUbjN0GO8Ob7Hutj` is enabled at `https://account.tomaspisar.cz/api/economysuite/stripe/webhook`, with checkout completion/async payment, refunds and dispute events. Its signing secret was neither read nor changed.

## Production checks and remaining limits

- Health, portal HTML, JavaScript and catalog return HTTP 200 with appropriate MIME types. Public catalog returns all three rank IDs, exact 3900/6900/9900 minor-unit prices, 604800 seconds and `checkoutable=true`; six pre-existing currency packages remain.
- Anonymous account remains HTTP 401; unsigned bridge POST remains HTTP 403. No authentication protections were weakened.
- Previous implementation validation remains: 97 focused plugin tests passed; full plugin suite 470/473 passed with three documented pre-existing failures; 80 backend and 106 website tests passed. This deployment changes configuration/documentation, not plugin bytecode or fulfillment logic.
- As expressly requested, no sandbox payment/refund was performed. No live payment was performed either. Full Paper/client cosmetic, inventory, perk and 30-player visual/load checks remain unperformed. Do not describe this as an end-to-end payment test.
- Existing ProtocolLib/Paper toast-adapter incompatibility disables only toasts; rewards/chat continue. The startup also logs an existing voicechat Paper-version parse error. These unrelated warnings were not patched during rank deployment.

## Recovery

To close new rank sales, set the production rank flag to false and deploy; existing paid order delivery must remain running. Do not delete financial records or restore an old database over later purchases. Keep the private pre-change backups out of Git. Reverting the JAR requires an explicit compatible-data assessment; do not blindly restore SQLite while the server is running.
