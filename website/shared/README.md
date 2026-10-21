# Shared Pantheon frontend

Canonical appearance assets for the homepage, wiki and player account. `design.css` owns the Chivo font, semantic light/dark colors, brand and native theme controls. `theme.js` runs before styles to avoid an incorrect initial theme. Login/register adapters change presentation only.

`next-steps.js` is a pure, read-only suggestion model loaded by the account overview. It filters stale/legacy/completed quests, uses existing level progress and accepts only fresh public registration state. It never sends an action or claims a reward. `surface.js` keeps the existing account consent controls while matching their copy and colors to the active Pantheon language/theme; it does not alter consent choices or handlers.

The preference is `light`, `dark` or `system` (default). System follows the operating system. A non-sensitive `pantheon-theme` cookie scoped to `pantheon.tomaspisar.cz` carries the choice between subdomains; local storage provides an origin fallback. Existing tabs recheck when focused. Both storage mechanisms may be blocked without breaking the current control. Only Pantheon hosts or explicitly marked local previews opt in. No account identifiers are stored here.

After editing canonical assets, run from the repository root:

```powershell
node website/scripts/sync-pantheon-design.mjs --wiki C:/Users/xpisa/PROJECTS/PantheonWiki
node website/scripts/sync-pantheon-design.mjs --wiki C:/Users/xpisa/PROJECTS/PantheonWiki --check
```

The account mirror is committed at `website/tomaspisar.cz/account/pantheon`; the separate wiki commits `assets/pantheon`. The homepage build copies canonical assets directly. Deploy each changed site independently. Keep site-specific layouts in each site's adapter, and preserve the font's OFL license.
