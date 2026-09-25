# Quick two-stat scoring — deployed 2026-09-25

- Active release: `/opt/telbattle/releases/20260925-quick-sum-v1`.
- Previous release: `/opt/telbattle/releases/20260925-collection-fixes-v1`.
- The nine overlaid backend, test, source, and frontend build files are listed
  with SHA-256 hashes in `QUICK_SUM_20260925_MANIFEST.json`.
- SQLite backup: `/opt/telbattle/backups/game_bot-before-quick-sum-20260925.db`,
  checked with `PRAGMA quick_check`. No explicit migration was needed.

## Rule

For every new Quick match, each card's score is the sum of its values in both
players' selected stats. Arena, passive, and opponent ability effects update
those values before addition. If both players select the same stat, that stat
counts twice for each card. Higher sum wins; equal sums tie. Matches already
started when the release was activated keep the previous single-stat rule.

Telegram's result message invites players to open its details button. The
report shows both component values, base and final sums, arena rules, and any
active passive or opponent ability effect. The Mini App result shows a short
rule description with an expandable calculation. Both surfaces preserve the
meaning of older stored reports. Arena text uses the saved match snapshot so
later rule edits do not rewrite the explanation of a completed fight.

## Verification

- Local Python suite: **176 passed, 1 skipped**. The skipped test requires a
  live Telegram session.
- VPS Python 3.9 staging suite: **176 passed, 1 skipped** using a temporary
  database. The pre-existing import logging `ResourceWarning` was ignored.
- Frontend `npm run build` succeeded. Existing font and onboarding image URLs
  remained external to the Vite bundle and resolve at runtime.
- All three services active with zero automatic restarts after activation.
  Public HTTPS health, `/miniapp`, and the new JavaScript asset returned HTTP
  200 from the VPS. The served JavaScript hash matched the staged manifest.
  No recent traceback/error log entries were found.
- No interactive Telegram match was played during verification.

## Rollback

Check the active release link, stop the three services, atomically point
`/opt/telbattle/current` to the previous release, restart the services, and
verify health. Preserve the live database: restoring the backup would discard
subsequent gameplay and is not required for a code rollback.
