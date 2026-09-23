# Game integrity fixes — deployed 2026-09-23

- Active release: `/opt/telbattle/releases/20260923-game-integrity-v1`
- Previous release: `/opt/telbattle/releases/20260922-tabletop-ui-v1`
- Public entry: `https://89-106-206-220.nip.io/miniapp`
- Restarted at 01:51:22 UTC: `telbattle-api`, `telbattle-bot`, `telbattle-admin`.
- The release was copied from the live release, then the seven backend files
  listed in `INTEGRITY_20260923_MANIFEST.json` were overlaid. Existing frontend,
  server configuration, and shared media were retained.
- Uploaded the test suite and its legacy migration import for staging QA.
- SQLite backup: `/opt/telbattle/backups/game_bot-before-integrity-20260923.db`;
  verified with `PRAGMA quick_check`. No explicit migration was run.

## Verification

- Staging on the production Python 3.9 runtime: 149 passed, 1 skipped.
  The skipped test requires a live Telegram session. Tests used a temporary
  working directory/database and a temporary pytest installation; the runtime
  environment's installed dependencies were unchanged. The pre-existing
  import-time logging `ResourceWarning` was ignored for this staging run.
- Uploaded file hashes matched the manifest before activation.
- Public HTTPS health: `{"status":"ok"}`; Mini App: HTTP 200.
- Public index SHA-256 matches the deployed frontend:
  `5ece355bf6ad99f56caaadc9c819ad8cc73c1cfc8481e40cb60864df56419903`.
- Unauthenticated profile request: HTTP 401; local admin page: HTTP 200.
- All three services are running with zero automatic restarts after deployment.

## Rollback

Verify `current` still points to this release before changing it. Stop the three
services, atomically replace `/opt/telbattle/current` with a fresh symlink to the
previous release, then start all three services and verify health. Preserve the
live database: restoring the backup would discard gameplay since deployment and
is not part of ordinary code rollback.
