# Independent product accounts

LongJumpReplay: https://ljr.tomaspisar.cz/login and `/register`; `/dashboard/*`.
EconomySuite: https://account.pantheon.tomaspisar.cz/login and `/register`; `/economysuite/*`.

The 2026-10-13 PANTHEON hostname change preserves the already-separated databases described below. Old `minecraft.tomaspisar.cz` pages redirect with 308; its API paths stay compatible with installed plugins and existing payment webhooks. This hostname-only change must not rerun the historical account-copy cutover below.

The licensing Worker serves both hosts, but authentication uses separate D1
databases. Minecraft auth tables are in `economysuite-player-portal` alongside
player data; LJR authentication/licensing stays in `longjumpreplay-licenses`.
Shared authentication code does not imply shared accounts. The host/trusted API
origin selects the database. A request body/query product selector cannot change it.
Session and CSRF cookies use product-specific `__Host-` names and no Domain attribute.
Sign-in, registration, password change/reset, logout and privacy requests stay in
their own database. The public site only links between systems.

Old `account.` pages redirect to the matching product. Its account APIs return 410;
no login or registration remains there. Signed EconomySuite bridge and payment
webhook paths remain compatible with already installed plugins and the existing
Stripe endpoint. New plugin defaults and canonical webhook URLs use `minecraft.`.
Keeping the old signed webhook avoids editing Stripe products or payment flows.
Games were disabled at the domain cutover; later explicit launch authorization is documented in ECONOMYSUITE_GAMES_LAUNCH.md.

## Cutover

1. Export both production D1 databases to the ignored
   `licensing-api/outputs/domain-split/` directory. Treat exports/plans as private:
   they contain personal data and password hashes. Do not commit them.
2. Apply EconomySuite migrations, including `0004_separate_accounts.sql`.
3. Deploy the new routing with `ECONOMYSUITE_ACCOUNTS_READY=false`, briefly pausing
   Minecraft account APIs while allowing the signed bridge/payment webhook.
   Deploy public assets containing the updated links and same-origin auth client.
4. Export fresh snapshots after old Minecraft signup/auth writes are stopped.
   From `licensing-api`, run `py -3 scripts/split-portal-accounts.py --ljr PATH
   --minecraft PATH --output outputs/domain-split/plan`. Inspect the summary.
   The script rehearses its SQL in local SQLite before writing a plan.
5. Import `copy-minecraft.sql` into Minecraft D1. Existing customer IDs, password
   hashes and timestamps are preserved. Player/order records are never rewritten.
   Sessions and one-time codes are not copied between products; sign in again.
6. Verify copied identities/credentials before importing `remove-ljr.sql` into LJR.
   Guards reject stale identities/passwords and accounts with LJR licences or
   orders. Only explicitly matched source IDs/emails are deleted.
7. Verify LJR removal, Minecraft retention and all original records associated with
   `xpisar10@gmail.com`. That address is excluded from every source update/delete;
   its original LJR account and records remain intact. It retains Minecraft access
   through the unchanged copied identity/password.
8. Deploy with the readiness setting enabled. Verify `/login`, `/register`, redirects,
   anonymous/private API behavior, signup boundaries, bridge status and assets live.

The reviewed initial inventory had seven shared customers, three Minecraft identities
(one protected), and two removable LJR copies with no LJR licences. The SQL plan is
generated from fresh snapshots rather than hardcoding these customer IDs.

If copying or guards fail, leave Minecraft APIs paused and investigate; never clear
the safeguards or erase the destination. D1 backups are retained locally for review.
Account removal was specifically requested for this domain/account split; this is
not a general change to the privacy-request retention workflow.

## Verified production result (2026-10-08)

Three Minecraft identities were copied with identical customer IDs, password hashes
and timestamps; player links, purchases and consents were unchanged. Two non-protected
LJR copies were removed, leaving five LJR accounts and three Minecraft accounts.
All protected customer-related records match the cutover snapshot byte for byte.
Between the initial backup and cutover, an existing protected session last_seen_at
advanced; no other protected record changed and the deletion changed none.

Backend deployment: `2a9319f3-66a0-4a73-ade7-47752cf21153`.
Website tests (75), Worker tests (56), typecheck, production build/deploy, activation
tests (24) and focused plugin tests/build passed. The full desktop pytest run stalled
after 48 tests and was stopped; it is not counted as passing. Plugin runtime testing
on Paper remains pending the server operator's EULA acceptance.

Live HTTP checks: anonymous account APIs 401 on both new hosts; retired auth API
410; wrong-product APIs 404; Minecraft catalogue 200; old login redirects 301.
Live browser checks verified both login brands, Minecraft registration and clean
redirect destination, with no console errors on registration.

Login retains a single compact card, product heading, email/password fields and
existing recovery/registration options. It retains the canonical product chooser. Forgot password, email-code login and
registration are hidden under Show other options. There are no explanatory
paragraphs, page navigation or footer. Product identity follows the host.

Final public asset deployment: `ed18868f-fae7-4efb-914a-4009fa4b8fcf`.
The minimal login composition was verified live on both canonical domains.
