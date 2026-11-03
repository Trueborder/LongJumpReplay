# EconomySuite bridge coordinator — 2026-11-03

User explicitly approved implementation, testing and deployment of the proposed free-plan SQLite Durable Object coordinator on 2026-11-03. This supersedes the earlier infrastructure approval block. No paid-plan change, D1 schema migration, game-server deployment or financial/gameplay test mutation is authorized or needed for this release.

## Implementation

- Front Worker forwards only the exact POST `/api/economysuite/bridge/poll`, `/api/economysuite/bridge/staff/poll` and `/api/economysuite/bridge/sync` routes, after existing host/product/admin guards and OPTIONS handling. It forwards the original signed body without buffering, parsing or resigning it. Snapshot sync was added after the first live rollout measured that route at 16 ms in the front Worker, revealing another CPU-limit risk in the same bridge.
- Production uses the bound `EconomyBridgeCoordinator` object named `pantheon`, the existing single game-server coordination boundary. Missing production binding fails closed with 503. Unbound development retains the existing direct handler.
- Coordinator admits only those three paths and POST. It invokes the existing EconomySuite handler with the existing D1 database, HMAC secret, timestamps, nonces, backoff, permissions, durable receipts and retry behavior. It cannot authenticate portal users. Signed acknowledgments and unrelated routes retain their existing routing.
- FIFO scheduling permits one active handler plus eight waiting requests. Waiters expire after five seconds with 503 and Retry-After: 10. Timed-out tasks are removed and never run later. Handler errors release the queue. An active database operation is not abandoned with a Promise.race, which would permit unsafe overlap. There is no per-request blockConcurrencyWhile or persistent copy of player data.
- Response header `X-ES-Bridge-Execution: coordinator-v1` identifies actual coordinator execution, including signed-verifier rejections. No credential or request-body logging.
- Production gains one Durable Object binding. Class migration `economy-bridge-coordinator-v1` declares a SQLite-backed class; existing D1/game databases are retained. No alarm, persistent object state, added service or subscription change.

## Baseline and scope

Pre-coordinator production baseline: `0370770f-13e7-47ab-b2a9-0b4bf22759ce`. Source-before snapshots, remote settings/deployment metadata and bundles are under `outputs/cpu-coordinator-20261103/`. Before-change local bundle exactly matches downloaded production bundle, SHA256 `98051b2bb881796c95b7bb3989259c0694c3a755031cb442377d3dffe65f8c53`.

Asset preflight built the same 47-file manifest as Wrangler (its reported 59 entries include directories). Cloudflare assets-upload-session reported zero missing asset hashes. No asset bytes were uploaded by that preflight. Preserve existing variables/secrets with --keep-vars and publish only the accounts/API Worker through Wrangler; do not use migrate-bearing deploy:production.

Baseline snapshot: `../../../../Website/qa/results/release/snapshot-1793718288299.json`. Cloudflare prohibits direct version rollback across a Durable Object class lifecycle change. Do not attempt a direct rollback to pre-class version 0370770f. The first coordinator-compatible version `f67ef0f3-fb39-4d5b-901f-b0e9445b3477` is the immediate rollback target for the sync follow-up, but it leaves snapshot sync at the old CPU boundary. A full behavior rollback requires a new validated deployment restoring the source-before routing while retaining the exported class, binding and existing migration history. Never delete the class/namespace or restore a database to undo this release. Reference: https://developers.cloudflare.com/workers/versions-and-deployments/rollbacks/.

## Validation before release

Ten new tests passed, including bundled actual Worker + SQLite Durable Object + real local D1 with all existing EconomySuite migrations. Coverage: both split polls, large signed runtime preservation across main heartbeat, heartbeat freshness, unsigned/stale/tampered/replayed rejection, backoff without nonce consumption, simultaneous polls/replays, pending-operation redelivery and signed acknowledgment, host/method/OPTIONS/non-poll boundaries, direct coordinator path rejection, missing production binding, bounded FIFO/overflow/wait expiry and recovery after handler failure.

The follow-up adds snapshot sync preservation, allowlist and force-refresh coverage plus the same invalid-signature/replay cases for that third route. After that change, all 72 affected bridge/staff tests passed, including 12 coordinator tests. Typecheck and final production dry run passed again.

Wrangler generated binding types, TypeScript typecheck and production dry run passed. The complete API suite passed: 261 tests in 34 files, including the ten new coordinator tests (211.68 seconds). Final release/live evidence will be recorded below. No test installation or dependency version change.

## Verification boundary

The earlier audit reports 787 resource failures in its preceding 24-hour analytics window. It did not attribute all failures to a specific route/function. After release, verify advancing signed bridge state and collect separate front-Worker and Durable Object outcomes/CPU metrics. An initial successful sample does not certify that daily alerts have ceased. A representative 24-hour active-traffic observation remains required; the daily email may still cover pre-release failures.

Reference: https://developers.cloudflare.com/durable-objects/platform/limits/ and https://developers.cloudflare.com/durable-objects/platform/pricing/. Free request/duration/storage quotas still apply. No billing upgrade is part of this implementation.

## First rollout and live measurements

Implementation commit `78ab024c`; first accounts/API version `f67ef0f3-fb39-4d5b-901f-b0e9445b3477`, deployed 2026-11-03 15:07:29 UTC with --keep-vars. No updated assets to upload. All 48 standard read-only live checks passed. Remote downloaded source exactly matches the validated bundle, SHA256 `130e1897cf5c858a4596ad5586447a6bbaebc86bc926d0e1897ef14ca24c41b3`. Binding comparison confirms only the coordinator was added; none removed or otherwise changed. Namespace API confirms use_sqlite=true.

Unsigned polls return 403 with coordinator-v1 header; the LJR host returns 404 without coordinator execution. Real signed bridge heartbeat advanced from 1793718498 to 1793718568, with age nine then two seconds. Staff revision=applied_revision=15, ready=true; monitor generation advanced from 1793718486 to 1793718556. These checks were SELECT-only, with zero rows written by the probes.

55-second live CPU tail at 15:10–15:11 UTC, all version f67ef0f3, all 200/ok:

| Route | Front Worker CPU (ms), five requests | Coordinator CPU (ms), five requests |
| --- | --- | --- |
| staff/poll | 0,0,0,0,1 | 13,9,13,10,8 |
| poll | 0,0,1,0,0 | 6,7,8,9,8 |

One player snapshot sync used 16 ms in the front Worker. The subsequent change routes it through the same coordinator, adding no new infrastructure or migrations. Do not call the first rollout a complete CPU fix.

Wrangler tail's actual timing field is cpuTime (milliseconds), not cpuTimeMs. Earlier audit parsers omitted that field; their claim that the tail lacked timing fields was a parser limitation. The corrected parser also uses entrypoint/durableObjectId to separate coordinator requests from front-Worker requests. Initial GraphQL aggregates can include both; do not treat their combined p50/p99 as front-Worker-only measurements. The separate Durable Objects GraphQL dataset returned no rows during the initial observation, so the per-route measurements above come from live tail.

## Follow-up deployment transition

Snapshot-sync change committed as `24ce566b`. Accounts/API version `35e0ba0e-566b-4578-89eb-58084c6a7cea` deployed 15:14:53 UTC with --keep-vars and no changed assets. All 48 standard read-only checks passed again. Remote source matches final tested bundle SHA256 `7f089319e946cea93eb251b4fee6189fbf7fea1f07b232f8f1757fc0d45f3dfd`; the coordinator remains the only binding addition relative to the original production baseline.

During 15:15–15:17 UTC, live tail confirmed front Worker version 35e0ba0e while the active coordinator still ran f67ef0f3. The old coordinator rejected the newly forwarded sync route with 404 (no handler, signature or D1 processing); polls continued 200/ok. This temporary failed sync interval must not be counted as successful release coverage.

Cloudflare's 2026-10-30 behavior change defers active Durable Object code updates by default for up to 300 seconds. Installed Wrangler 4.123.0 does not expose the new immediate-update CLI option; no incidental tooling upgrade was made. The release must wait for actual class-version adoption and verify real sync success, not just a successful Worker deployment. For future route additions, deploy an accepting coordinator first and observe its new version before routing the new path, or use verified newer tooling's explicit immediate strategy. Reference: https://developers.cloudflare.com/changelog/post/2026-10-30-durable-objects-deferred-code-updates/.

## Final runtime verification — completed

Actual new coordinator version was observed by 15:20:07.581 UTC. The following successful signed requests were observed on final version 35e0ba0e from then through 15:21:21 UTC:

| Route | Successful signed requests | Front Worker CPU | Coordinator CPU |
| --- | ---: | --- | --- |
| staff/poll | 8 | 1–2 ms | 9–22 ms |
| poll | 8 | 1 ms | 6–15 ms |
| sync | 2 | 1–3 ms | 13–16 ms |

All eighteen signed exchanges returned HTTP 200/outcome ok in both front Worker and coordinator. No resource-limit/exception outcome in the post-adoption tail. The larger CPU work now executes under the Durable Object allowance; front-Worker requests in this sample are below 10 ms. This is an initial active-traffic observation, not 24-hour certification or a claim about every unrelated API route.

All three unsigned signature probes return 403 with coordinator-v1, no-store; the temporary 404 interval has recovered. SELECT-only D1 checks across final rollout show heartbeat 1793718968 → 1793719218, monitor generation 1793718926 → 1793719176 and latest player snapshot 1793718859 → 1793719209. Staff revision and applied_revision stay 15, ready=true. Final heartbeat age was nine seconds. No game or financial action was initiated to test the release.

Evidence: `final-cpu-tail.json` retains the transition and per-event version/entrypoint/CPU/status without headers or bodies. `final-summary.json` isolates successful final-version post-adoption exchanges. `final-db-first.json`, `final-db-last.json`, `final-integrity.json` and `final-security-probes.json` record the corresponding checks, under `outputs/cpu-coordinator-20261103/`.

The final aggregate GraphQL request hit the account's query-budget limiter (retry after five minutes). No retries were made against that limit; do not report aggregate post-release error counts or separate Durable Objects GraphQL metrics as verified. Runtime evidence above comes from actual Wrangler live tail and read-only D1 queries. No paid upgrade was performed; the existing worker usage model and variables remain unchanged. Authenticated portal browser coverage and a representative 24-hour active-traffic result remain unverified. Daily summary mail can still include failures from before release or the documented sync transition.
