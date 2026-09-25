# Deck card-form clarity — deployed 2026-09-25

- Active release: `/opt/telbattle/releases/20260925-deck-form-clarity-v1`.
- Previous release: `/opt/telbattle/releases/20260925-deck-final-reveal-v1`.
- Changed backend and test files are listed with SHA-256 hashes in
  `DECK_FORM_CLARITY_20260925_MANIFEST.json`.
- SQLite backup: `/opt/telbattle/backups/game_bot-before-deck-form-clarity-20260925.db`;
  `PRAGMA quick_check` passed. No schema migration was needed.

The reported Deck round compared two copies of John Wick: the challenger's
Normal form had 85 popularity, and the opponent's Legend form had 100. The
existing Deck resolver correctly used each player's owned card form. The
result message previously omitted the form, making the different values look
wrong. Round results now show each card's form and explain when the same
character has different forms. The final selection status also uses the
player's owned form. Deck scoring rules remain unchanged.

Verification: local and staged VPS Python suites each passed **182 tests**;
one live Telegram test was skipped. After activation, all three services were
active with zero automatic restarts, no recent error-level journal entries,
public HTTPS health returned `{"status":"ok"}`, and `/miniapp` returned 200.
No interactive Telegram match was played during verification.

To roll back, stop the three services, atomically point `/opt/telbattle/current`
to the previous release, then restart and check health. Keep the live database;
restoring the backup would discard gameplay after deployment.
