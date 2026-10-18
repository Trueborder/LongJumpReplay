# Pantheon rank page and details — 2026-10-18

The final user preference is to keep ranks entirely out of Store. Store retains coin/token packages and the free daily website reward; no active-rank panel, comparison or rank cards are rendered there. The navigation now includes **Ranky / Ranks** at `/economysuite/rank`.

## Presentation

- VIP: yellow crown; VIP+: green shield; MVP: light-blue gem. Repo-native SVG symbols need no new images or dependencies. Existing portal layout, fonts and reduced-motion policy remain.
- The public Rank page includes compact cards and a coloured semantic comparison table. Each card opens a native dialog with all thirteen benefit rows, including inherited cosmetics and shared-booster restrictions. Both views use the same benefit definitions.
- Prices and checkout availability come from the existing catalog, not a new payment source. Preview sends no mutation. An order closes the detail dialog and opens the existing consent form with fresh unchecked boxes; visitors are directed to sign-in or player pairing when needed.
- Dialogs use native focus containment/Escape and restore focus to the card. The table has an independently scrollable, labelled keyboard region on narrow screens. CZ/EN text and login return destinations include the new route.

## Validation

- JavaScript syntax check, TypeScript check and production Wrangler dry-run passed.
- Website: **113 tests passed**, including rendered comparison/details, all inherited benefits, three distinct symbols, configured colours, price escaping, public route allowlists, disabled-purchase conditions and an initial-render click-through test from card to details to consent with no payment request.
- Backend: **80 tests passed**. These are automated local tests, not sandbox or live payment transactions. No Stripe products, financial rules, secrets or database schemas were changed.
- Existing navigation, appearance expiry, daily claims, payment consent and refresh tests remain passing. A prior expiry fixture was moved from Store to Appearance because Store intentionally no longer renders the active-rank panel.

## Production verification

Deployed account assets and Worker together as version `b72e57bd-4b5c-48bd-8d2e-00ff11f3e0a2`. The live Rank route, cache-busted JavaScript and styles are HTTP 200 with their correct MIME types. Browser inspection of Store confirmed six currency cards, zero rank cards, no comparison and no active-rank panel.

Verified native MVP detail opening, all thirteen benefit rows, Escape closing and focus restored to the original rank card. English VIP+ detail and Czech language restoration worked. At 1280 pixels, the three cards are side-by-side with the specified distinct accents; at 390 pixels, document width remains 390 and the open dialog fits from X=19 to X=371. Screenshots are saved outside Git at `C:/Users/xpisa/Documents/Codex/Pantheon-rank-page-2026-10-18/`. Actual account payment submission was not performed.

No Minecraft JAR or server restart is required. Existing account/private API authorization remains unchanged.
