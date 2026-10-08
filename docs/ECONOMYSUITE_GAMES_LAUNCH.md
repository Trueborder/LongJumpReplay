# EconomySuite public games deployment

On 2026-10-08 the owner answered "Public launch — launch review is complete" and
explicitly requested publication. The owner will install the server JAR. This
records the owner's confirmation; it is not an independent legal/platform review.

The production web/API is deployed at https://minecraft.tomaspisar.cz/economysuite/games.
Worker production settings enable games only on the canonical Minecraft origin.
LJR accounts, existing Stripe products/prices and purchase flows are unchanged.
No customer credentials, account records or balances are changed during activation.

## Server handoff

Install EconomySuite 2.29.1 on the existing Paper 1.21.11 / Java 21 server with Vault.
Stop the server cleanly, back up its plugin JAR/config/database, replace the old
EconomySuite JAR, and merge these settings into the existing config.yml:

```yaml
website:
  enabled: true
  environment: production
  games-enabled: true
  games-test-enabled: false
  portal-origin: 'https://minecraft.tomaspisar.cz'
```

Preserve the existing bridge secret (or ECONOMYSUITE_BRIDGE_SECRET environment
variable) and all other configuration. Do not replace the full config with the
snippet. Start the server normally; do not use Bukkit /reload. Wait for its signed
poll before checking the Games page as a linked player.

Migration 0005_games_activation.sql gives bridge_status.games_enabled a default
of zero. New bets require a recent signed poll with games_enabled=true and rules
version es-games-1. An old plugin, disabled flag or disconnected server cannot
accept new bets. Supported plugins continue retrieving pending rounds even after
disabling games, allowing committed results to be synchronized safely.

## Verification and rollback

Website tests, Worker tests/typecheck and focused plugin activation/settlement tests
must pass before deployment. Actual Paper/server acceptance remains the operator's
handoff: inspect startup logs, link a player, verify a completed round and exact
balance change, then verify reload/retry returns the same round. Do not claim these
live gameplay checks were done by this release.

To stop new betting set the Worker ECONOMYSUITE_GAMES_ENABLED=false and deploy,
or set website.games-enabled=false and restart Paper. Keep the supported plugin and
bridge running to resolve pending rounds; never delete/requeue a round based only
on a timeout. Retain the databases and durable round IDs when rolling back.

## Deployment evidence (2026-10-08)

- Backend version: 7d2e9f49-43df-4f3f-be2e-2a1f8259863a; production games flag true.
- Public asset version: bf73dec0-d0db-4cf3-84d3-5b4cf7ea2d6e.
- Production migration 0005 applied successfully. Read-only bridge check reports
  es-games-1 with games_enabled=0, so server installation/activation remains pending.
- Games page redirects anonymous users to the Minecraft login (302); games script
  returns 200 text/javascript; private config rejects anonymous access (401).
- Website: 75 tests passed. Worker: 57 tests and typecheck passed. Plugin: 7 focused
  activation/settlement tests and shadowJar passed under JDK 21. Formatting checks
  passed. No live bet was placed and no customer credentials/balances were modified.
- JAR SHA-256: 910fc05aebe5ff88450cc8bf7ad6a371235b40a44a32d2752b6b15ba16fae8da.

The local Paper rehearsal now uses Minecraft-scoped test sessions and reports
explicit activation. Its actual runtime acceptance remains pending operator EULA
acceptance; a syntax check is not counted as a Paper runtime pass.
