# Trial progression release — 2026-10-01

Active release: `/opt/telbattle/releases/20261001-trial-progression-v2`.
Previous release: `/opt/telbattle/releases/20260928-progression-economy-v1`.
Pre-activation SQLite backup: `/opt/telbattle/backups/game_bot-before-trial-20261001.db`.

This release adds transactional request receipts for Fusion and coin Upgrade, trial Level Coin and Mode rules, and a mission for every one of the 101 catalog characters. Mini App and bot confirmations pass request keys; a matching retry replays the committed outcome, while key reuse with a different action is rejected. Match wins advance eligible card missions in the same reward transaction. The trial route gives a new player 100 Coin at Level 2, enough for the current 100-Coin Normal-to-Epic upgrade after approximately ten ordinary wins. Mini App three-round PvP opens at Level 2 and Easy at Level 3; Quick and Deck remain Level 1, Risk remains Level 7. XP thresholds and Upgrade prices did not change.

The trial mission manifest uses three wins for starter characters John Wick, Heisenberg and Rehi and five wins for all other characters. Mission claim still requires the Epic form and awards its existing Legend form and 30 XP. Existing Level 2+ accounts receive no retrospective Level Coin payout; the rules reward future level crossings. The normal Score-to-Coin conversion and other economy paths remain as before.

The VPS snapshot preflight applied all 101 missions and trial rules while preserving 21 players, 101 catalog characters, 11,670 Coin, 597 Score and 13,565 XP. `PRAGMA quick_check` remained `ok`, and the 79 pre-existing foreign-key violations did not increase. Windows Python 3.12 and staged VPS Python 3.9 each passed **242 tests** with **1 skipped** live Telegram test. The Mini App TypeScript/Vite build passed. After activation, the API, bot and admin services were active with zero restarts; local API health returned `ok`, and `/miniapp` returned HTTP 200. No real player match or Claim was triggered for verification.

Card art remains separate: the active catalog has 303 forms, of which 203 still point at the placeholder and three Subzero T forms have no image path. The exact backlog is `content/card_art_backlog_2026-10-01.json`. Existing Normal artwork contains printed rarity and statistics, so it was not reused as Epic/Legend art. No new art was deployed in this release.

Rollback: stop `telbattle-api`, `telbattle-bot`, and `telbattle-admin`; atomically point `/opt/telbattle/current` to the previous release; restart and check health. The Level/Mode rule changes are reversible through `scripts/configure_trial_progression.py` or by restoring the backup while services are stopped. Restoring that backup after gameplay resumes would discard intervening player activity, so treat it as recovery rather than routine code rollback.
