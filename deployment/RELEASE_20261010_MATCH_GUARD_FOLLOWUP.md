# Match management guard follow-up — 2026-10-10

Runtime commit: `b08e628031234c26facb6e7a4f94f9ccc89e9f48`. This release follows the [coordinated collaborator rollout](RELEASE_20261010_COLLABORATOR_PHASES.md). No new collaborator commit or open PR was present when checked before and after this follow-up.

## Player behavior and fix

The v2 economy's extra state scan treated an unstarted Easy lobby, an expired Quick/Easy choice and a cancelled request's retained snapshot as an active match. Separately, the shared guard missed joined Easy players because they are stored in `state.players`, not `game_requests.opponent_id`.

`ProgressionEconomy.active_guard` now uses the shared `CardUpgradeSystem._active_match` decision. That decision includes Easy participants and checks request status, terminal phase and a valid remaining deadline. It remains read-only. A live match still prevents card changes; a stale snapshot or unstarted lobby does not create a lock. Existing accepted Deck handling and match result/payout logic are preserved.

The fix does not alter XP, Coin, prices, unlock levels or the five feature flags. The owner chose to keep the current rules and leave the proposed economy disabled.

## Validation

- The new management matrix reproduced **10 failures in 12 cases** before the fix. After the fix, all cases pass with v2 enabled and disabled, covering both participants and an unrelated user.
- A Flask API regression verifies that an upgrade is rejected during live Quick, succeeds after the choice deadline, and retries without consuming more copies or granting more XP.
- A fresh tester lifecycle uses real temporary SQLite and Flask API, a new account with zero Coin, three starters and an initial deck. Completed-match input, claim dates and random draws are controlled. It covers XP, level Coin/slots, duplicate claims, Epic upgrade, sale, quoted purchase and Easy/Deck unlock, including retries. It does **not** constitute live Telegram gameplay or a browser connected to production.
- Final guarded Windows Python 3.12 suite: **517 passed, 2 skipped**. The disposable database root also contained `TEMP`, `TMP` and `TMPDIR`; an initial invocation without those Windows temp overrides was rejected by the guard during a migration dry-run, then corrected.
- Main [CI run 38042541065](https://github.com/kasra-dastranj/telegram-card-game-bot/actions/runs/38042541065): Python 3.11 and 3.9.25 each **518 passed, 1 skipped**; frontend/admin JavaScript, release package and CI gate successful. The downloaded Python 3.9.25 XML records 519 total tests, zero failures/errors.
- The 14 new scenarios also passed on actual VPS Python 3.9.25 in a separate directory, run as `telbattle` with clean runtime files, offline network guards and temporary SQLite. No live account or database was used by these tests.
- Graphify's local AST graph was updated after the code changes.

## Exact artifact and activation

- Source SHA: `b08e628031234c26facb6e7a4f94f9ccc89e9f48`
- Artifact: `release-b08e628031234c26facb6e7a4f94f9ccc89e9f48-1`
- Run/attempt: `38042541065` / `1`
- Archive SHA-256: `26ca6db199ea8d604c6cbb02f5be8af5b816f995389be12d478db4354fa02bd6`
- Policy: `database_policy=no-change`, 96 runtime files plus `RELEASE.json`
- Active release: `/opt/telbattle/releases/actions-38042541065-1-b08e62803123`
- Previous release: `/opt/telbattle/releases/actions-38040508402-1-379153d12994`
- Pre-activation backup: `/opt/telbattle/backups/before-actions-38042541065-1.db`

The owner invoked the reviewed restricted Actions sender/receiver with this exact successful main artifact. The server held the shared deployment lock, passed startup preflight on a SQLite copy, backed up the live database, switched code and verified internal health. No migration or feature activation was applied. This is an owner-triggered restricted release, **not** a completed manual GitHub Deploy workflow started by the collaborator. The protected production environment's approval rules were unchanged.

A machine-local Windows wrapper restricted the temporary SSH key's ACL. Its first ACL invocation failed before SSH; the corrected SID syntax was retried successfully. No private key or wrapper is tracked in Git, and the Linux Actions sender/installed receiver were not changed for this issue.

The receipt reported `status=ok` and `internal_health=ok`. Post-activation checks verified all 96 runtime hashes and the active pointer against deployment state. `telbattle-bot`, `telbattle-api` and `telbattle-admin` were active with `ExecMainStatus=0` and `NRestarts=0`; API health was `ok` and SQLite `quick_check=ok`.

All five flags remain false: `progression_v2_enabled`, `custom_cards_enabled`, `quick_friendly_enabled`, `easy_custom_cards_enabled`, `custom_card_orders_enabled`.

## Remaining data and product work

The 79 existing foreign-key violations remain unchanged. A read-only production check located 5 `active_fights → players`, 33 `battle_states → active_fights`, 36 `round_history → active_fights` and 5 `rare_cards_info → cards` violations. This release did not delete, reconstruct or rewrite those records.

Balance approval, legacy-account progression policy, Legend A/B content, owner-supplied artwork, custom-card product decisions and live tester QA remain as recorded in [section 6 of the development report](../docs/PROGRESSION_ECONOMY_DEVELOPMENT_2026-09-28.md). The collaborator-started Actions workflow still requires its first complete owner-approved execution.

Code rollback uses the recorded previous release and the shared lock. It never restores the database automatically; the original October 7 release must also remain available because preserved configuration/static links reference it.
