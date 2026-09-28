"""Verify and activate the staged progression release on the TelBattle VPS."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path("/opt/telbattle")
CURRENT = ROOT / "current"
PREVIOUS = ROOT / "releases/20260925-abilities-v1"
RELEASE = ROOT / "releases/20260928-progression-economy-v1"
DATABASE = ROOT / "shared/game_bot.db"
BACKUP = ROOT / "backups/game_bot-before-progression-20260928.db"
MANIFEST = RELEASE / "deployment/PROGRESSION_20260928_MANIFEST.json"
SERVICES = ("telbattle-api", "telbattle-bot", "telbattle-admin")


def verify_release() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for relative, expected in manifest.items():
        path = RELEASE / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("staged file hash mismatch: " + relative)
    print("Verified staged files:", len(manifest), flush=True)
    return len(manifest)


def snapshot(conn: sqlite3.Connection) -> dict[str, int]:
    queries = {
        "players": "SELECT COUNT(*) FROM players",
        "owned_characters": "SELECT COUNT(*) FROM player_cards",
        "decks": "SELECT COUNT(*) FROM player_decks",
        "coins": "SELECT COALESCE(SUM(coins),0) FROM players",
        "score": "SELECT COALESCE(SUM(total_score),0) FROM players",
        "xp": "SELECT COALESCE(SUM(total_xp),0) FROM player_progression",
    }
    return {name: int(conn.execute(sql).fetchone()[0]) for name, sql in queries.items()}


def verify_database(path: Path, *, migrate: bool) -> dict[str, int]:
    with sqlite3.connect(str(path)) as conn:
        before = snapshot(conn)
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("database integrity check failed")
        previous_foreign_key_errors = set(conn.execute("PRAGMA foreign_key_check").fetchall())
    if migrate:
        sys.path.insert(0, str(RELEASE))
        from core.database import DatabaseManager
        DatabaseManager(str(path))
    with sqlite3.connect(str(path)) as conn:
        after = snapshot(conn)
        if before != after:
            raise RuntimeError("player economy changed during schema migration")
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("migrated database integrity check failed")
        foreign_key_errors = set(conn.execute("PRAGMA foreign_key_check").fetchall())
        if foreign_key_errors - previous_foreign_key_errors:
            raise RuntimeError("migration introduced foreign key violations")
        if foreign_key_errors:
            print("Pre-existing foreign key violations:", len(foreign_key_errors), flush=True)
        if migrate:
            stacks = conn.execute(
                "SELECT COALESCE(SUM(quantity),0) FROM player_card_stacks"
            ).fetchone()[0]
            if int(stacks) < before["owned_characters"]:
                raise RuntimeError("card inventory migration lost ownership")
            for table in ("match_reward_events", "weekly_reward_batches",
                          "level_coin_rules", "mode_unlock_rules"):
                if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone():
                    # Match/weekly ledgers are initialized by their services.
                    if table not in ("match_reward_events", "weekly_reward_batches"):
                        raise RuntimeError("missing schema: " + table)
    print("Preserved players, cards, decks, Coin, Score and XP:", after, flush=True)
    return after


def switch(target: Path) -> None:
    temporary = ROOT / "current-progression-20260928.tmp"
    if temporary.exists() or temporary.is_symlink():
        raise RuntimeError("unexpected temporary release link")
    temporary.symlink_to(target)
    os.replace(str(temporary), str(CURRENT))


def service_health() -> None:
    for service in SERVICES:
        state = subprocess.check_output(
            ["systemctl", "is-active", service], text=True
        ).strip()
        if state != "active":
            raise RuntimeError("service not active: " + service)
    with urllib.request.urlopen("http://127.0.0.1:5001/api/v1/health", timeout=10) as response:
        if json.load(response).get("status") != "ok":
            raise RuntimeError("API health failed")


def activate() -> None:
    if CURRENT.resolve() != PREVIOUS:
        raise RuntimeError("live release changed; refusing to overwrite")
    if BACKUP.exists():
        raise RuntimeError("backup path already exists")
    verify_release()
    switched = False
    services_stopped = False
    backup_ready = False
    try:
        services_stopped = True
        subprocess.run(["systemctl", "stop", *SERVICES], check=True)
        with sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(str(BACKUP)) as destination:
                source.backup(destination)
        BACKUP.chmod(0o600)
        verify_database(BACKUP, migrate=False)
        backup_ready = True
        verify_database(DATABASE, migrate=True)
        subprocess.run(["chown", "-hR", "telbattle:telbattle", str(RELEASE)], check=True)
        switch(RELEASE)
        switched = True
        subprocess.run(["systemctl", "start", *SERVICES], check=True)
        for attempt in range(12):
            try:
                service_health()
                break
            except Exception:
                if attempt == 11:
                    raise
                time.sleep(2)
        print("Active release:", CURRENT.resolve(), flush=True)
        print("Database backup:", BACKUP, flush=True)
    except Exception:
        if switched:
            switch(PREVIOUS)
        else:
            # No new service has written to the database yet; restore the exact
            # stopped-service snapshot if the schema migration failed.
            if backup_ready:
                with sqlite3.connect(str(BACKUP)) as source:
                    with sqlite3.connect(str(DATABASE)) as destination:
                        source.backup(destination)
        if services_stopped:
            subprocess.run(["systemctl", "restart", *SERVICES], check=True)
            print("Previous release restored", flush=True)
        raise


if __name__ == "__main__":
    if sys.argv[1:] == ["verify"]:
        verify_release()
    elif sys.argv[1:] == ["activate"]:
        activate()
    else:
        raise SystemExit("usage: activate_progression_20260928.py verify|activate")
