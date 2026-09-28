# Progression and economy integration — deployed 2026-09-28

- Active release: `/opt/telbattle/releases/20260928-progression-economy-v1`.
- Previous release: `/opt/telbattle/releases/20260925-abilities-v1`.
- Live SQLite backup: `/opt/telbattle/backups/game_bot-before-progression-20260928.db` (`PRAGMA quick_check` passed).
- The staged package carried 200 hashed files; the release manifest is `deployment/PROGRESSION_20260928_MANIFEST.json` inside the VPS release.

The release unifies match XP/Score settlement, adds replay-safe weekly and match rewards, migrates card ownership to per-character/per-form quantities, fixes starter decks and daily Claim, and adds configurable Level Coin and Mode unlock rules. The bot, Mini App API and frontend build were deployed together. Default Mode gates remain Quick/Deck/Easy/Mini three-round at Level 1 and Risk at Level 7; no new Level Coin amounts or Upgrade prices were activated. Two existing card images needed by the importer tests were copied into the shared image directory. The importer now accepts that directory's symlink while rejecting other escapes from the project.

Local Python 3.12 and staged VPS Python 3.9 suites each passed **234 tests**, with **1 skipped** live Telegram test. The Mini App TypeScript/Vite build passed. Migration on a SQLite snapshot and again during activation preserved 21 players, 66 owned characters, 12 decks, and the aggregate Coin, Score and XP balances. The live database had 79 pre-existing foreign-key violations; the migration introduced none. The cause of those legacy violations remains to be audited separately.

After activation, `telbattle-api`, `telbattle-bot` and `telbattle-admin` were active with zero automatic restarts. Public HTTPS `/api/v1/health` returned `{"status":"ok"}`; `/miniapp` and the new JavaScript bundle returned HTTP 200. No real player match or Claim was triggered for verification.

Rollback: stop all three services, atomically point `/opt/telbattle/current` to the previous release, then restart and verify health. Keep the live database when rolling back code so gameplay after this release is not discarded. The pre-release SQLite backup is for recovery if needed, not an automatic code rollback.
