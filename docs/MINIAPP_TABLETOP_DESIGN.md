# Mini App: tabletop redesign

## Direction

Make the collection and the act of playing a card the primary visual identity.
The lobby uses a fan of the player's actual cards, restrained brass accents,
warm charcoal surfaces, and the bundled Vazirmatn font. Avoid oversized slogans,
neon glass panels, fabricated online counts, and decorative resource dashboards.

## Implementation boundaries

- `frontend/game/src/tabletop.css` contains the tabletop theme and its responsive
  adjustments, imported after the existing structural and onboarding styles.
- `main.ts` renders the owned-card preview, consistent four-stat card footers,
  game-specific navigation, daily reward shortcut, and empty-deck illustration.
- Preview requests use the existing paginated cards API with `limit=3`. They do
  not block startup or overwrite the full playable hand. A request generation
  prevents late responses replacing newer previews. Empty inventories show card
  backs, never fictional owned cards. Returning to the lobby refreshes the preview.
- `BattleScene.ts` keeps registry background URLs and versions intact, dims only
  the arena art, and improves solo card scale, typography, and rarity colors.
  Reduced-motion users skip solo card entrance animation.
- Finished solo matches disable stat buttons during the result transition, so
  another move cannot be submitted after game over.
- No economy, server API, arena registry contract, or database changes are needed.
- Existing card illustrations are reused. Frames/text baked into an illustration
  remain part of that source image; replacing them is a separate asset task.

## Verification

From `frontend/game`, run `npm run build`, then `npm run preview -- --host 127.0.0.1`.
The browser scripts use local demo data or intercepted API fixtures; they do not
modify production accounts. On Windows they use an installed Edge/Chrome browser.

```powershell
$env:QA_URL = 'http://127.0.0.1:4173/miniapp-assets/'
node scripts/qa-redesign.mjs
node scripts/qa-drag.mjs
$env:QA_URL = 'http://127.0.0.1:4173/miniapp-assets/?demo=1&dense=1'
node scripts/qa-player-hub.mjs
$env:QA_URL = 'http://127.0.0.1:4173/miniapp-assets/?demo=1'
node scripts/qa-lobby.mjs
node scripts/qa-onboarding.mjs
```

Coverage includes 360/375/390px phones, tablet, landscape guard, reduced motion,
keyboard focus, 44px lobby touch targets, loaded Persian font, no horizontal
overflow, empty/one/two-card inventories, search/filters, card details and upgrades,
deck creation/deletion, claims, skins, Fusion confirmation, drag rejection and
acceptance, hand pagination, Quick completion, and a best-of-three solo result.

Inspect the actual artwork screenshots under `frontend/game/test-results/redesign-after/`.
The other suites store screenshots in `test-results`, `qa-artifacts`, or `tmp`.
Screenshot review remains necessary: DOM bounds alone do not detect canvas cards
being covered by HTML controls. Check both the shortest phone and tablet battle.

## Release

Deploy the complete Vite `dist` output, including existing fonts, onboarding,
and arena media, using the established VPS release workflow. Local verification
is not production deployment or Telegram-device verification.
