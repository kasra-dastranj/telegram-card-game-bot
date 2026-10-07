# Collaborator changes — deployed 2026-10-07

Reviewed branch: `collab/mohammadhosein-mirzanezhad`.
Deployed source commit: `1b87fc7e5554ab721e190029adcbb402bf8482be`.
The owner's local `main` was fast-forwarded to the collaborator's commits, preserving authorship and history.

## Changes reviewed

- `72e0e0b`: `bot/main.py` configures the root logger only when it has no handlers. Importing the bot during pytest no longer constructs an unused `bot.log` file handler. An ordinary standalone bot launch retains its existing file and stream logging.
- `1b87fc7`: the card support editor can add a custom Trait, automatically select it while preserving existing selections, and save it with the character family. Enter adds the Trait without submitting the form. Blank names are rejected; names matching an existing option case-insensitively reuse it. Opening another card resets the choices so an unsaved custom option does not leak between editors. Saved Traits appear in the API options and remain available after reload.
- The existing card-family API test now verifies storing a Persian custom Trait and returning it in the editor options. There is no new battle rule, mode, economy setting, schema migration or card-content import. Adding a label does not define a new gameplay rule for that label.

## Validation

- Windows Python 3.12: **247 passed, 1 skipped**; the skipped check requires live Telegram access.
- Staged VPS Python 3.9: **247 passed, 1 skipped**, using an isolated writable SQLite snapshot and a separate QA environment. An initial staging attempt could not write a SQLite journal in the root-owned backups directory; moving the test database to a dedicated directory owned by the service account resolved this test setup issue.
- Card editor JavaScript passed `node --check`.
- Chrome/Playwright on disposable local data verified custom Trait creation, preservation of existing selections, blank and duplicate inputs, Enter behavior, save/reload persistence and switching cards without leaking an unsaved option. Desktop and 390-pixel mobile viewport checks passed with no page JavaScript errors or mobile horizontal overflow. Screenshots are local, ignored artifacts in `deployment/artifacts/`.
- On a copy of the current VPS database, the admin HTML, `/api/cards` and `/api/card-editor/options` returned HTTP 200. Before/after catalog and economy checks preserved 22 players, 101 characters, 303 forms, 11,995 Coin, 600 Score and 13,720 XP. SQLite `quick_check` returned `ok`; the 79 existing foreign-key violations did not increase.

## VPS activation

Active release: `/opt/telbattle/releases/20261007-collaborator-card-traits-v1`.
Previous release: `/opt/telbattle/releases/20261001-card-admin-v3`.
Verified pre-activation backup: `/opt/telbattle/backups/game_bot-before-collaborator-20261007.db`.

The staged release copies the previous deployment and overlays only `bot/main.py`, `web/card_management.html` and `tests/test_card_admin_api.py`. The two production files and changed test were checked against the reviewed Git baseline before staging; all three new file hashes were checked before activation. Existing server configuration, shared image links and frontend build are preserved. Tests use the isolated database; the release database link is restored to `/opt/telbattle/shared/game_bot.db` before activation. No real player action or live card edit was used for verification.

After an atomic switch of `/opt/telbattle/current`, `telbattle-bot`, `telbattle-api` and `telbattle-admin` were active with `ExecMainStatus=0` and `NRestarts=0`. The Mini App health endpoint reported `ok`; the updated admin HTML and both catalog endpoints returned HTTP 200 on their internal ports.

Rollback: stop the three TelBattle services, atomically repoint `/opt/telbattle/current` to the previous release and start the services, then verify API and admin health. This release requires no database rollback. Restoring the backup after gameplay would discard subsequent player activity and is only for data recovery.
