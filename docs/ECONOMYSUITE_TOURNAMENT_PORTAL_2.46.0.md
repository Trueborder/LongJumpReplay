# Tournament portal 2.46.0

The implementation and activation contract is documented in the EconomySuite repository at `docs/TOURNAMENT_PORTAL_2.46.0.md`.

- Player page: `https://account.pantheon.tomaspisar.cz/economysuite/tournament`.
- Owner administration: `https://account.pantheon.tomaspisar.cz/economysuite/tournament-admin`.
- Apply `licensing-api/economysuite-migrations/0009_tournaments.sql` to the EconomySuite D1 binding before deploying the account Worker/assets.
- Existing web credentials, secrets, Stripe products, flags and normal gameplay snapshots are reused and preserved.
- The verified email `xpisar10@gmail.com` is pinned once to stable customer ID on the first authenticated request; future recreation of the same email does not gain access. As requested on 2026-10-20, the signed-in owner no longer needs a secondary password prompt. Owner authorization, authenticated session, CSRF, destructive confirmations, operation idempotency and revision checks remain mandatory. The retired reauthentication endpoint returns 404; its additive legacy table is left intact. Turnaj-admin navigation is returned by the backend, never inferred from a browser email field.
- Screenshots with fixture players prove responsive layout and browser behavior, NOT real tournament synchronization. Actual Minecraft visuals, the post-login inventory UI and all live admin operations require the new JAR and a separate Paper smoke test.

## Delivery evidence

The owner explicitly approved a private ignored production D1 export and deployment. Backup is under `licensing-api/.wrangler/backups/` and is never staged. Migration 0009 was the only pending migration and was applied successfully; original order/consent/financial-operation/player-link counts stayed 21/19/97/9 and `PRAGMA foreign_key_check` was clean.

Final account Worker/assets deployment: `ba85fbf7-eecd-4e24-aa85-d85bf29c5933`. JS/CSS/tournament asset HTTP 200/source hashes matched; anonymous tournament API=401, protected pages=302 to login, unsigned tournament bridge=403. No authenticated live mutations, payments or game-server restart were performed. Install EconomySuite 2.46.0 for the first actual tournament snapshot.

Validation: 121 website tests; the 92-test complete backend suite and 9 final targeted tournament tests; TypeScript, JS syntax and deployment dry run. Isolated Chrome at 1440px/390px confirmed bracket connectors, skin crop rendering, modal/Escape, translations and polling without losing edited values. The plugin release records its own Java/Paper verification separately.
