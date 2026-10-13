# PANTHEON domain layout

## Production mapping

- Minecraft: `pantheon.tomaspisar.cz` (DNS only).
- EconomySuite account: `https://account.pantheon.tomaspisar.cz` (Workers Custom Domain).
- Map: `https://map.pantheon.tomaspisar.cz` (Exaroton HTTPS, internal port 80).
- Intended wiki: `https://wiki.pantheon.tomaspisar.cz` (GitBook; provider setup required).

## DNS and dynamic Exaroton routing

The owner verified actual Minecraft connectivity through `pantheon-test.tomaspisar.cz` before cutover. Both production aliases use Exaroton's dynamic records, never a fixed IP or port:

| Type | Owner | Target |
| --- | --- | --- |
| CNAME, DNS only | pantheon.tomaspisar.cz | pnthsmp.exaroton.me |
| CNAME, DNS only, not flattened | _minecraft._tcp.pantheon.tomaspisar.cz | _minecraft._tcp.pnthsmp.exaroton.me |
| NS | map.pantheon.tomaspisar.cz | galileo.exaroton.com |
| NS | map.pantheon.tomaspisar.cz | columbus.exaroton.com |

Parent `pantheon.tomaspisar.cz` must not retain NS delegation: it would shadow the account and wiki records. Only map is delegated. Squaremap keeps its existing renderer/world options and HTTP listener on 0.0.0.0:80; settings.web-address is `https://map.pantheon.tomaspisar.cz`.

The map requires an online server. No always-running host or tunnel was added. HTTPS certificates may take time to provision; never bypass certificate validation while checking readiness.

## Portal compatibility

The account Worker and public asset Worker must both be deployed. Existing D1 IDs, customer accounts, payment configuration and signed plugin bridge credentials are unchanged. Old minecraft.tomaspisar.cz pages redirect while preserving path/query; API requests are handled without redirects. Cookies are host-only, so users sign in again on the new hostname.

## Rollback

If Minecraft connectivity regresses, remove only the two production CNAME aliases and restore the original two DNS-only NS records at pantheon.tomaspisar.cz pointing to galileo.exaroton.com and columbus.exaroton.com. This restores Minecraft routing but shadows all descendants again, so revert public links and account canonical origin together. Do not delete databases, change fixed game ports, or touch unrelated mail/website DNS.

Portal code can be rolled back to its previous Worker version. Restore the previous canonical origin and public asset version at the same time. GitBook content must remain intact; do not purchase or change its plan without owner approval.
