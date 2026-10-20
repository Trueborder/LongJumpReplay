# PANTHEON homepage changelog

## 2026-10-20 — Production domain cutover

- Verified real signed exports after the owner's JAR installation and published the homepage on pantheon.tomaspisar.cz with HTTPS.
- Backed up DNS and replaced only the root web record; preserved Exaroton's independent SRV alias. Minecraft protocol status checks pass before and after; account/wiki/map remain available.
- Added a fixed anonymous service-binding request, supported manual redirect rejection and browser-cache bypass while keeping ten-second internal caching. All 139 website tests pass. Actual Minecraft client login and active tournament/community runtime checks remain unverified.

## 2026-10-20 — Golden Pantheon homepage and public event summary

- Added independent Czech/English homepage, original temple illustration, responsive navigation, joining instructions, feature guides, Discord/account links and accessible FAQ.
- Added privacy-safe signed aggregate export and anonymous summary endpoint with stale-data handling, plus a fixed same-origin cached homepage proxy.
- Published a noindex preview and deployed the API after its sole additive migration. Existing portal, wiki and map remain unchanged; game DNS cutover awaits the owner's JAR installation and real export verification.
