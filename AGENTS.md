## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Personal collaborator branches

If the checked-out branch starts with `collab/`, read `COLLABORATOR_START_HERE.md` before working. Keep all work on that personal branch, bring in owner changes with `git fetch origin main` and `git merge origin/main`, and verify every completed commit is pushed to the same branch. Do not push to `main`, force-push, merge a PR, deploy to the VPS, or use production credentials from a collaborator branch. The owner's normal `main` workflow is unaffected.

## Reviewed Actions releases

After owner review and merging to main, a collaborator with Write may manually dispatch `Deploy TelBattle` from main, using the protected production Environment. This exception applies only after the owner completes and approves bootstrap in `docs/DEPLOY_FROM_GITHUB_FA.md`; never dispatch production during implementation or before that approval. It does not permit direct SSH, root access, retrieving production data/secrets, bypassing branch protection, or deploying a collaborator branch. Workflows, deployment helpers, access policies and bootstrap changes require owner review. CI must remain offline with temporary SQLite databases and no production secrets. Server-side manual owner releases must hold `/opt/telbattle/deploy.lock`; automatic rollback restores code only, never post-start player data.
