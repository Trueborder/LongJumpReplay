# PANTHEON Survival homepage

Standalone static CZ/EN site with an independent Cloudflare Worker. Existing account, wiki, map and checkout remain separate.

## Visual direction

The homepage uses a monumental Pantheon wordmark, warm stone surfaces, charcoal text, a moss action accent, self-hosted Chivo, and the existing voxel illustration as a panorama. Feature routes and joining instructions use editorial layouts rather than repeated cards. `PRODUCT.md` records existing product facts and constraints; `DESIGN.md` records the replacement visual system. Taste Skill supplied the composition direction, Impeccable the quality floor, and Emil's guidance the interaction details. The new design preserves the independent status proxy and all account/wiki/map/Discord destinations.

## Build and preview

Shared theme assets live in `../shared/pantheon`; `../shared/README.md` documents synchronization to the account and separate wiki checkout. The homepage build copies these directly. All three sites offer Light / Dark / System, localized to Czech/English where available. Theme choice is shared across Pantheon subdomains. Release 2026-10-21 versions: homepage `86f5457a-52c1-462d-a464-60292ec36123`, account `32000fcb-79ce-4421-b90b-b726c2571178`, wiki `5246ac53-f414-4c96-a9b4-ba960f5223ca`. These supersede the historical deployment records below.

Run from this directory (custom build commands use the current directory):

```powershell
node build.mjs
& ../../licensing-api/node_modules/.bin/wrangler.cmd deploy --dry-run
& ../../licensing-api/node_modules/.bin/wrangler.cmd dev --port 8833 --local --compatibility-date 2026-08-18
```

The local date override is required by the currently installed older workerd. Production uses the configured 2026-10-20 date. `dist/` is generated and ignored. Tests run from `website` using `node --test tests/*.cjs`.

Edit `assets/content.mjs` for both languages, version labels, links, FAQ and feature copy. Keep the illustrated hero labelled as original art, not an actual server screenshot. Navigation uses native disclosures, visible keyboard focus and a mobile menu; CSS-only intro/press feedback respects reduced motion and keyboard input. Live refreshes never replay entrance effects. Fonts are self-hosted; accompanying OFL licenses must remain with them.

## Public API

Latest journey/discovery release (2026-10-21): homepage `3136ea1a-0763-4717-83a9-b5128f319e89`, account `2417f4b2-c6db-4b42-aea3-792809fe14e0`, wiki `7cd64405-e542-4ea9-b049-92be534316ee`. Joining links now lead to `/zacni-tady`; account linking still requires confirming the actual player and finishing in Minecraft. No server PIN belongs in a website form.

Status recovery: `availability` is `live`, `waiting`, `disabled` or `stale`; a network failure is shown locally as unreachable. An intentionally stopped server naturally stops publishing snapshots. Check the public timestamp and the main bridge heartbeat before diagnosing an export fault; do not change timestamps or extend freshness to disguise a stopped bridge. The anonymous endpoint is no-store, the homepage Worker retains a ten-second edge cache, and the browser expires a fresh display at 30 seconds, polls while visible, checks again when network/visibility returns and offers a seven-second-bounded manual retry. Old timestamps include their date. The production test start restored fresh zero-player snapshots without any backend/plugin repair.

`GET /api/economysuite/public/summary` lives in the account Worker and is separately projected from authenticated responses. It returns `version:1`, `updated_at`, `fresh`, `server`, `tournament`, `community`. The latter three are null when export is disabled, absent or older than 30 seconds. Zero players is a valid online count. Finished/expired goals and nonpublic tournament phases are omitted.

The signed `POST /api/economysuite/bridge/public/sync` accepts a versioned snapshot with `enabled`, server aggregate (players, capacity, version), tournament aggregate (phase, enrolled count, size, BO, mode/policy, reward summary) and community aggregate (title, progress, target, deadline). Ingest and read use the same idempotent allowlist; no player identities, IPs, inventories, operations or catalogue are returned.

Homepage `GET /api/status` fetches only the fixed public API URL, forwards no cookies, refuses redirects and uses a ten-second edge cache. It never proxies arbitrary paths or caller-supplied URLs. The browser refreshes every 15 seconds while visible, revalidates age and handles unavailable data without made-up counts. All dynamic text is escaped. CSP permits only same-origin assets and scripts.

## Plugin and migration

- EconomySuite 2.46.2 adds `website.public-summary-enabled: true`; absent keys default to true. It still requires the existing enabled signed website bridge. Preserve its origin and secret.
- Export uses the existing async bridge timer. Bukkit and tournament data are copied on the main thread; community totals use a single SQL aggregate off-thread. Export failure is caught separately and does not stop pairing or purchases.
- Apply only `licensing-api/economysuite-migrations/0010_public_summary.sql` before the account Worker deployment. It adds one table with one current snapshot; no existing rows are transformed.
- A private ignored D1 export was saved before applying this migration. Do not commit or publish it. Foreign-key validation after application returned no violations.

## Deployment status — 2026-10-20

- Preview: https://pantheon-home.xpisar10.workers.dev/ (CZ), `/en/` (EN). Workers.dev responses carry `X-Robots-Tag: noindex`.
- Production: https://pantheon.tomaspisar.cz/ and `/en/`. Homepage Worker version after the visual redesign: `f25beacc-8f40-49b5-ac39-4431b86f7188`.
- Account API version: `33b1904d-38dd-409b-a898-99bc32554409`.
- At domain cutover, the owner installed the JAR and restarted; repeated real exports returned `fresh:true`, Java 1.21.11, zero players and capacity 20. At redesign validation the feed is stale (`fresh:false`), so the homepage reports live status unavailable. Export freshness is separate from the visual release. No fake snapshot was inserted.
- The root web CNAME was backed up and replaced with the homepage custom domain. The independent Minecraft SRV CNAME is unchanged, including its record ID and modification timestamp. Before/after protocol status handshakes through the original address both returned Paper 1.21.11. No additional restart was performed.
- Homepage uses a service binding to `longjumpreplay-licensing-production`, calling only the fixed anonymous GET on `account.pantheon.tomaspisar.cz`. No incoming cookies or paths are forwarded. Redirect mode is `manual`, with non-2xx responses rejected: Workers does not support `redirect:error`. Backend authentication is unchanged.

## DNS cutover and rollback

The previous root CNAME was `pantheon.tomaspisar.cz -> pnthsmp.exaroton.me`, DNS-only, TTL 60. The current root is Cloudflare's managed proxied AAAA placeholder for the homepage custom domain. Minecraft SRV discovery remains delegated through the separate DNS-only CNAME `_minecraft._tcp.pantheon.tomaspisar.cz -> _minecraft._tcp.pnthsmp.exaroton.me`. Preserve the latter unchanged, including CNAME flattening disabled. Never hardcode Exaroton's current address or port. The pre-cutover backup is `outputs/pantheon-dns-before-cutover-20261020.json` in the Codex task directory, outside this repository.

1. Owner installs only EconomySuite 2.46.2 in place of the old EconomySuite JAR, preserving the plugin data folder, then restarts.
2. Verify actual `fresh:true`, aggregate counts, tournament/community behavior and no leakage in the public endpoint.
3. After that check, replace only the root web CNAME with the homepage Worker custom domain. Add `{ "pattern": "pantheon.tomaspisar.cz", "custom_domain": true }` to this Worker's `routes`; do not touch account/wiki/map records or Minecraft SRV discovery.
4. Verify HTTPS, CZ/EN canonical URLs, API/assets and a real Minecraft Java client connection through the same address, including Exaroton SRV resolution. Snapshot freshness does not prove a client login.
5. If game connection or HTTPS fails, detach the new Worker custom domain and restore the original root CNAME/content/TTL/proxy state from the backup. Leave the Minecraft SRV alias intact throughout.

## Validation

- All 137 website tests and all 99 Worker tests passed; TypeScript and production dry runs passed.
- Chrome checked desktop and 390px mobile, loaded fonts/images, no horizontal overflow, clipboard success, mobile menu/Escape, language changes preserving the section and no console errors. Reduced-motion policy and clipboard fallback are covered by automated source checks, not claimed as manually emulated browser states.
- Signed API round-trip tests cover unknown/disabled export, zero counts, stale data, active/expired goals, unsafe input and existing private-route authentication.
- Java: 615 tests pass with only the two pre-existing OrdersDatabaseTest cases requiring live Paper registries excluded by an external test init script. The initial complete run contained 617 tests and failed those same two cases. No exclusion was added to repository build configuration.
- Cutover validation: 139 website tests pass, production HTTPS CZ/EN/status/account/wiki/map return 200, Chrome visibly shows real online status and no active events. Browser requests bypass local cache; only the Worker's internal cache retains responses for ten seconds, with no-store headers returned to clients even on cache hits. Both pre/post Minecraft protocol status checks pass using dynamically resolved SRV. Actual authenticated Minecraft client joining and active event rendering on Paper were not performed; the server has no active event to inspect.

## Artwork

Generated using the built-in imagegen tool. Original source remains in the Codex generated_images folder. Project-bound variants: `assets/pantheon-hero.webp` (1672×941, 238346 bytes), `assets/pantheon-mobile.webp` (900×507, 86728 bytes), `assets/pantheon-og.jpg` (1200×630, 194928 bytes). Resizing/compression did not change the illustration's scene. Temple logo is repo-native SVG.

Final generation prompt:

> Use case: stylized-concept. Asset: original panoramic hero illustration for the PANTHEON Survival Minecraft Java server website. Premium cinematic Minecraft voxel art, NOT a website mockup and NOT a screenshot of any real server. Scene: an ancient Greek-inspired golden-lit stone temple with six block-built columns on a lush raised grassy rocky island, medieval merchant stalls with burgundy and ochre cloth canopies below, paths and a small waterfall. Two small Minecraft adventurers in the foreground, one with a diamond sword and one holding a pickaxe; no combat violence. Wide 16:9 composition, principal temple and stalls on the RIGHT two-thirds, LEFT third is quiet dark blue mist/landscape with generous negative space for website text. Golden sunset from upper right, rich obsidian navy shadows, warm amber/orange lanterns, vibrant green grass, stone and wood block textures, dramatic but inviting handcrafted environment. Crisp isometric-ish 3D voxel render with beautiful depth, layered floating terrain, subtle clouds. No lettering, no logos, no UI, no HUD, no watermark. All illustrated objects square block-based in recognizable Minecraft visual language. Do not copy any existing server artwork.
