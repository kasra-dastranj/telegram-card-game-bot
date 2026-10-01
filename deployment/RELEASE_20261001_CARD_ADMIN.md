# Card support editor release — 2026-10-01

Release path: `/opt/telbattle/releases/20261001-card-admin-v3`.
Previous path: `/opt/telbattle/releases/20261001-trial-progression-v2`.
Pre-activation SQLite backup: `/opt/telbattle/backups/game_bot-before-card-admin-20261001.db`.

The support editor now saves a character's Normal, Epic, and Legend definitions together. Shared story/mode metadata remains on the character; stats, card type, abilities, legacy effects, passive, image path, and Telegram media belong to each form. Form switches preserve unsaved entries. A new character requires explicit stats for all three forms. The family API validates first and commits all writes in one SQLite transaction, preserving existing card and variant IDs. Legacy endpoints remain available. The editor offers choices for traits, effects, series, image paths, and passive condition values.

No schema migration or card art import is part of this release. The card images symlink continues to point to `/opt/telbattle/shared/card_images`. After deployment, check that `/api/card-editor/options` and `/api/cards` respond through the protected admin service, then verify all three services. Do not create or modify a live card for smoke testing.

Validation: `python -m pytest -q` on Windows and on the staged VPS release passed 247 tests with one skipped live Telegram test; admin HTML JavaScript passed `node --check`. On a SQLite copy of the live catalog, the staged admin returned HTTP 200 for `/api/cards` and `/api/card-editor/options`. After activation, those two routes and the admin HTML returned HTTP 200, the Mini App API returned `{"status":"ok"}` from `/api/v1/health`, and the admin, API, and bot services were active with zero restarts. No live card was modified for smoke testing.

Rollback: atomically restore `/opt/telbattle/current` to the previous release and restart the API, bot, and admin services. This release does not alter the database until an administrator edits a card. Restoring a database backup after gameplay would discard intervening player activity; use it only for recovery.
