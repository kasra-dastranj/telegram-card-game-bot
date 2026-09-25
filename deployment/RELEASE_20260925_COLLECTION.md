# Collection and skin fixes — deployed 2026-09-25

- Active release: `/opt/telbattle/releases/20260925-collection-fixes-v1`.
- Previous release: `/opt/telbattle/releases/20260923-game-integrity-v1`.
- Services activated at 08:14:57 UTC: `telbattle-api`, `telbattle-bot`, `telbattle-admin`.
- The release copies the previous release and overlays the seven files in
  `COLLECTION_20260925_MANIFEST.json`; hashes were verified before activation.
- SQLite backup: `/opt/telbattle/backups/game_bot-before-collection-20260925.db`,
  verified with `PRAGMA quick_check`. No explicit schema migration was needed.

## Fixes

- My Cards and `/cards` no longer wrap an already constructed Telegram keyboard.
  The production exception was reproduced with real Telegram update objects and
  mocked network transport.
- Collection pagination supports old buttons, empty categories, Rare cards, and
  returning to the main menu. Read-only collection buttons work in older messages.
- Card detail, favorite, legacy card view, mission reward, and skin callbacks
  preserve identifiers containing underscores. Dynamic card text is HTML escaped.
- Favorites show the player's upgraded rarity and variant stats; rarity counts
  use player overrides. Both historical loss spellings count in the summary.
- Skin refresh no longer mutates immutable Telegram callback objects. Old skin
  buttons remain supported while new buttons use unambiguous skin identifiers.
- Bot skin purchases use the transactional purchase shared with the Mini App:
  concurrent duplicate purchases charge once, failed inventory writes roll back,
  free skins work, and negative prices are rejected. Activation validates card
  ownership and the skin's associated card.

## Verification

- Local Python 3.12: **171 passed, 1 skipped**.
- VPS Python 3.9 staging: **171 passed, 1 skipped**, using temporary databases and
  the existing temporary pytest installation. The pre-existing logging
  `ResourceWarning` was ignored on staging, as in the previous release.
- Added 22 regression cases, including real immutable Telegram update objects,
  full skin purchase/activation/deactivation, concurrent purchases, and an
  injected SQLite write failure. No Telegram messages were sent by these tests.
- The skipped test requires a live Telegram session; no interactive Telegram
  verification was performed.
- All three services active, zero automatic restarts, no recent traceback/error
  entries after activation. Local API health passed.
- Public HTTPS `/api/v1/health` and `/miniapp` returned HTTP 200 from the VPS.
  The workstation's DNS resolved the hostname to an unexpected private address,
  so public access from that network was not confirmed.

## Rollback

Verify `current` still points to this release, stop the three services, atomically
replace `/opt/telbattle/current` with a fresh symlink to the previous release,
then start the services and verify health. Preserve the live database: restoring
the backup would discard gameplay since deployment and is not a code rollback.
