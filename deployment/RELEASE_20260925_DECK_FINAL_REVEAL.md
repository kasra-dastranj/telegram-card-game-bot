# Deck final-round card reveal — deployed 2026-09-25

- Active release: `/opt/telbattle/releases/20260925-deck-final-reveal-v1`.
- Previous release: `/opt/telbattle/releases/20260925-quick-sum-v1`.
- Changed backend and test files are listed with SHA-256 hashes in
  `DECK_FINAL_REVEAL_20260925_MANIFEST.json`.
- SQLite backup: `/opt/telbattle/backups/game_bot-before-deck-final-reveal-20260925.db`;
  `PRAGMA quick_check` passed. No schema migration was needed.

In every Deck variant, the sole remaining card in round three is still
selected by its player. Its inline image and name are visible as soon as that
player sends it. In the fallback button path, the bot posts the selected card
to the group immediately. The shared status panel names a card after its
player selects it. Other rounds and non-Deck modes retain their prior behavior.

Verification: local and staged VPS Python suites each passed **181 tests**;
one live Telegram test was skipped. After activation, all three services were
active with zero automatic restarts, no recent error-level journal entries,
public HTTPS health returned `{"status":"ok"}`, and `/miniapp` returned 200.
No interactive Telegram match was played during verification.

To roll back, stop the three services, atomically point `/opt/telbattle/current`
to the previous release, then restart and check health. Keep the live database;
restoring the backup would discard gameplay after deployment.
