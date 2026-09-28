"""Test the additive migration against a SQLite snapshot, never the live DB."""

from __future__ import annotations

import sqlite3
import os
import tempfile
from pathlib import Path

from activate_progression_20260928 import DATABASE, ROOT, verify_database, verify_release


def main() -> None:
    verify_release()
    fd, name = tempfile.mkstemp(
        prefix="game_bot-staging-progression-20260928-", suffix=".db",
        dir=ROOT / "backups",
    )
    os.close(fd)
    staging_database = Path(name)
    with sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(str(staging_database)) as destination:
            source.backup(destination)
    staging_database.chmod(0o600)
    print("Staging database:", staging_database, flush=True)
    verify_database(staging_database, migrate=True)


if __name__ == "__main__":
    main()
