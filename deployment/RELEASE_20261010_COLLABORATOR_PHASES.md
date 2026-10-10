# Coordinated collaborator release — 2026-10-10

PR [#1](https://github.com/kasra-dastranj/telegram-card-game-bot/pull/1) was reviewed and merged into `main` as `1395cf403e123e8d1d96b9ae08931f79c558385e`, preserving the collaborator's commits. The deployed runtime is `379153d1299478685bfcad6a756b1e1f012dda01`, including two fixes found during owner verification.

## Released behavior

- Custom Trait names have an independent persistent registry. Removing a Trait from every card, deleting a card or restarting no longer removes its name from the editor choices.
- Mini App three-round PvP and ASO practice can use an ability once per match from the shared Quick inventory. Consumption, retry protection, arena changes and opponent reveal use server state.
- The Phase 1 shared card origin/match policy contracts and the Phase 2/3 progression/custom-card schemas and code are installed. **The owner explicitly chose to preserve the existing economy for this rollout.** `progression_v2_enabled`, `custom_cards_enabled`, `quick_friendly_enabled`, `easy_custom_cards_enabled` and `custom_card_orders_enabled` all remain false. No new prices, XP curve, mode levels, paid custom orders or Friendly behavior were enabled for players.
- GitHub CI, the protected production environment and the restricted SSH deployment entrypoint are configured. `main` requires `CI gate`, one review and a code-owner review. Production permits only branch `main` and requires the owner, with self-review prevented. Deployment secrets are environment secrets; no root key is shared with the collaborator.

## Fixes discovered during integration

1. `c07d848`: a mobile browser check exposed intermittent scrolling failure during match polling. The frontend now preserves the battle scroll container and avoids replacing unchanged battle markup; PvP and ASO share the fix. The browser regression check verifies that the container remains connected across polling.
2. `379153d`: the clean preflight environment deliberately has `PATH=/usr/bin:/bin`, but the VPS account-switching utility is `/usr/sbin/runuser`. The receiver now uses that absolute path. A regression test verifies the privileged launcher while retaining the clean unprivileged environment.

## Validation and data preservation

- Windows Python 3.12, collaborator integration: **502 passed, 2 skipped**. After the receiver fix, the release tests separately passed **15 tests, 1 skipped**.
- Final main [CI run 38040508402](https://github.com/kasra-dastranj/telegram-card-game-bot/actions/runs/38040508402): Python 3.11 and server Python 3.9.25 each passed **504 tests, 1 skipped**, with frontend, packaging and CI gate successful.
- Full isolated suite on the actual VPS Python 3.9.25: **504 passed, 1 skipped**. Offline guards restricted SQLite to disposable storage and blocked external network access.
- Local build used the project's supported Node 24.19.0. Admin JavaScript syntax passed. The existing runtime asset warnings remain; static/media links on the VPS preserve those resources.
- Browser checks passed for progression/custom-card mock scenarios, three mobile viewport sizes and ASO abilities saved for round two. They verified polling, scroll retention, ability use and subsequent stat selection. They did not create a real player battle or edit a live card.
- Trait/foundation/progression/custom migrations first passed against a SQLite snapshot. During a maintenance window under `/opt/telbattle/deploy.lock`, they were applied after a fresh SQLite backup. Hashes of every row projected through the original columns of all **47 existing business tables** remained identical. Preserved totals: 22 players, 101 characters, 303 forms, 11,995 Coin, 600 Score and 13,720 XP. `quick_check=ok`; the 79 pre-existing foreign-key violations did not increase. All new feature flags remained off. A subsequent isolated startup preflight confirmed no further logical database changes.

## Deployed artifact and server state

Artifact source: the final successful main CI, not a PR merge-preview artifact.

- SHA: `379153d1299478685bfcad6a756b1e1f012dda01`
- CI run: `38040508402`, attempt `1`
- Runtime files: 96, plus `RELEASE.json`
- Archive SHA-256: `2f50ce629e786a2e7607c9b980fef2f8072a7551c3f479e3e826a05ab8d9edf5`
- Active release: `/opt/telbattle/releases/actions-38040508402-1-379153d12994`
- Previous release: `/opt/telbattle/releases/20261007-collaborator-card-traits-v1`
- Pre-migration backup: `/opt/telbattle/backups/before-phases-20261010.db`
- Pre-activation backup: `/opt/telbattle/backups/before-actions-38040508402-1.db`

The owner invoked the reviewed Actions sender/receiver directly with the exact successful main artifact. This tested the dedicated forced-command SSH account, lock, receipt, backup, preflight and activation path; it was **not** a completed manual GitHub Deploy workflow run. The first Windows sender attempt failed before receiving a server receipt. A local owner-only wrapper applied a Windows ACL to the temporary SSH key, and the retry succeeded. The Actions runner is Linux, where the sender's existing mode-0600 handling applies.

The final receiver receipt reported `internal_health=ok`. All three services were active, `ExecMainStatus=0` and `NRestarts=0`. The API, admin HTML/catalog/options and Mini App internal checks passed. HTTPS through the local Nginx returned 200 for Mini App and the expected 401 for the protected admin. All 96 deployed runtime hashes matched the recorded manifest. No production database, private card image or secret is included in the archive.

Private media storage is `/opt/telbattle/shared/private_custom_media`, owned by `telbattle` with mode 0700. A separate systemd environment file sets that path without replacing existing configuration or tokens. Private/custom features remain disabled.

## Future deployment and rollback

The collaborator can dispatch **Deploy TelBattle** on `main` after the PR is merged. The workflow runs CI/build/package, then waits for the owner's production approval. Deployment is queued and server operations share `deploy.lock`. See [current deployment status and commands](../docs/DEPLOYMENT_STATUS_2026-10-10_FA.md).

Rollback restores the recorded previous code release under the lock and checks health; it does not restore the database. Keep the additive schemas and disabled flags. Restoring a SQLite backup after gameplay requires separate owner recovery review because it would discard subsequent player activity. The prior release must remain available: preserved config and static links still reference it.
