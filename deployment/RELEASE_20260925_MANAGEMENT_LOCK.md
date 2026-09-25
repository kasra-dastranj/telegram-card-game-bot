# Mini App collection lock fix — deployed 2026-09-25

- Active release: `/opt/telbattle/releases/20260925-management-lock-v1`.
- Previous release: `/opt/telbattle/releases/20260925-deck-form-clarity-v1`.
- Changed backend and test files are listed with SHA-256 hashes in
  `MANAGEMENT_LOCK_20260925_MANIFEST.json`.
- SQLite backup: `/opt/telbattle/backups/game_bot-before-management-lock-20260925.db`;
  `PRAGMA quick_check` passed. No schema migration was needed.

The Mini App's deck creation, card claims, upgrades, fusion and skin actions
shared one collection-management lock. It treated every accepted/active
`game_requests` row as a live match forever. Deck requests remain `accepted`
after the corresponding fight ends, and Quick choices can remain `active`
after their deadline when a scheduled timeout is lost. This blocked a player
with no live fight. The reported account had 15 accepted Deck requests and one
old Quick choice; its recent Solo matches were completed and its PvP fight was
cancelled.

The lock now uses `active_fights` for Deck, the invite deadline for an accepted
Quick request, and the saved choice deadline for active Quick/Easy matches.
Active fights and live timed choices still protect the collection. Stale
request records remain in history but no longer block management.

Verification: local and staged VPS suites each passed **185 tests**; one live
Telegram test was skipped. A read-only check against the live database with
the staged and active code returned `False` for the reported account's
management lock. After activation, all three services were active with zero
automatic restarts and no recent error-level journal entries. Public HTTPS
health returned `{"status":"ok"}` and `/miniapp` returned 200. No real card
claim or deck change was made during verification.

To roll back, stop the three services, atomically point `/opt/telbattle/current`
to the previous release, then restart and check health. Keep the live database;
restoring the backup would discard gameplay after deployment.
