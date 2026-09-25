# Mini App three-round PvP — deployed 2026-09-25

- Active release: `/opt/telbattle/releases/20260925-three-round-pvp-v1`.
- Previous release: `/opt/telbattle/releases/20260925-management-lock-v1`.
- Files and SHA-256 hashes: `THREE_ROUND_PVP_20260925_MANIFEST.json`.
- Database backup: `/opt/telbattle/backups/game_bot-before-three-round-pvp-20260925.db` (`PRAGMA quick_check` passed). No schema migration was needed.

The Mini App's three-round button now opens a choice between real random matchmaking, a friend invite link, and the existing ASO practice mode. Real matches use the same one-card, fixed-arena, unused-stat-per-round calculation as ASO practice. Choices are persisted, scoped to the two players, hidden until the opposing choice is made, and resolved on the first two round wins or after three rounds. Each choice has a 60-second deadline; a player who does not choose forfeits. The result shows both players' base values, arena boosts, totals and round scores. Active matches can be resumed after leaving or reloading the Mini App.

Quick and three-round requests now have separate API scopes, including invite acceptance. The new match does not grant Solo practice rewards or consume its daily Solo quota.

Verification: local suite **189 passed, 1 skipped**; TypeScript/Vite production build passed. Staged Python 3.9 smoke test completed a full match against an isolated temporary database. After deployment, all three services were active, public HTTPS health returned `{"status":"ok"}`, `/miniapp` and its new JS bundle returned 200, and the API journal showed no recent error-level entries.

Rollback: stop the three services, atomically point `/opt/telbattle/current` to the previous release, restart them, and verify health. Keep the live database; restoring the backup would discard gameplay since deployment.
