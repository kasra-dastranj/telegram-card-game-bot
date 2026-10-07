# Actions deployment preparation — 2026-10-07

This change prepares CI, reviewable artifacts and a restricted manual release path. It does not install the server bootstrap or activate a production release. The currently confirmed deployment remains source `1b87fc7e5554ab721e190029adcbb402bf8482be`, with the owner's report at main `752ee2d4a30405213c3d0cafbe1147d91093ce7a`.

## Local validation

- Windows Python 3.11.9, offline CI guard enabled: **259 passed, 3 skipped**. Skips are the opt-in live Telegram check, Linux flock, and unavailable Windows directory symlinks. This is a fresh run, not the prior release's result.
- Node 24.19.0 / npm 11.17.0: `npm ci` and `npm run build` succeeded. Existing local sparse/static asset resolution warnings remain; the server deployment preserves these durable paths by reference.
- Admin inline JavaScript passed `node --check`. CI passed actionlint with no ignores; deploy passed with only the known `queue` grammar diagnostic ignored. The current actionlint release predates GitHub's documented `concurrency.queue: max`; this one option was verified against [GitHub's current concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency). No other lint errors are suppressed.
- Disposable package tests reject changed runtime files, tampered hashes, extra secrets, traversal, links and duplicate members. WAL backup, preflight startup on synthetic SQLite, migration rejection on a copy, recovery after backup failure and code rollback preserving post-start data passed. Linux flock is exercised in real GitHub CI.
- Graphify was updated; tracked code is tested independently of the ignored graph outputs.
- After the full run, the local real bundle check found a clean CRLF checkout differing from raw Git bytes in a legacy HTML file. Packaging now uses Git's worktree filters to detect changes and copies canonical commit blobs through one batched Git process. The added EOL regression and the final helper suite passed **14 tests, 1 skipped** on Windows. The latest whole-tree Linux suite is checked in the PR CI.

`npm audit` reports four existing high-severity entries: vite, nanoid, postcss and source-map-js. This work does not update the frontend dependency graph. The owner should review the registry advisories and dependency updates separately; do not apply an unreviewed audit fix in the release job.

## Delivery and activation gates

The PR's Actions checks and downloadable `release-*` artifact are the evidence for actual Linux/Python 3.9.25 validation. Their final links and results are recorded in the PR description after completion. Production has not been dispatched as part of this preparation.

The owner must review/merge this PR, require `CI gate` plus owner approval on main, configure the production Environment's main-only branch policy, install the disabled forced-command receiver, review the preserved path map and dedicated SSH key/host key, then enable the receiver. Exact commands and limits are in [the Persian guide](../docs/DEPLOY_FROM_GITHUB_FA.md).

Automated deployment rejects schema/data changes and changed runtime requirements. Existing server configuration, shared media, database and service units are preserved. Root-owned deployment records detect concurrent manual pointer changes; all owner manual releases must use the same flock. Rollback changes code only and does not restore the player's newer database state.

## Follow-up: permanent custom trait vocabulary

The user reported that a custom trait disappeared when removed from the last card. Follow-up commit `c2e684af6d9053d509203e3a9d00d461b87b8b95` adds a separate permanent registry and immediate registration from the UI. It requires an owner-reviewed additive SQLite migration before deploying that code; see [the trait guide](../docs/CARD_TRAITS_FA.md). The Actions receiver's no-change guard remains enabled and rejects unprepared databases. Existing card/player data stays unchanged; names already lost before this fix must be added again.

The full Windows suite passed 274 tests with 3 skips; the final admin suite passed 21 tests. GitHub run 37642218615 passed 276 tests with 1 live-Telegram skip on both Python versions, plus frontend build and inline JS validation. That first run ended unsuccessfully before scheduling packaging and subsequent rerun requests returned HTTP 500. This is not reported as a fully passing CI run; the final PR check must also include packaging and CI gate. Its local source bundle was independently verified with 80 runtime files, no secrets or production data, and database_policy=no-change. The PR description carries the latest complete CI evidence when GitHub completes it.
