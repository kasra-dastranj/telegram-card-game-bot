"""Reviewed additive Phase 1 migration; preview a SQLite backup before --apply."""
import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from migrations.migrate_card_trait_registry import copy_database
from systems.shared_foundation import ensure_foundation_schema, settings_in


def apply_migration(database):
    path = Path(database).resolve(strict=True)
    with closing(sqlite3.connect(str(path), timeout=30)) as conn:
        if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise RuntimeError('SQLite integrity check failed')
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            ensure_foundation_schema(conn)
            settings_in(conn)
            if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('Migration integrity check failed')
        return conn.execute('SELECT COUNT(*) FROM cards').fetchone()[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview-copy', type=Path)
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.apply and not args.backup:
        parser.error('--apply requires a new --backup destination')
    if args.preview_copy and args.backup:
        parser.error('--backup is only for --apply')
    try:
        if args.preview_copy:
            target = copy_database(args.database, args.preview_copy)
        else:
            copy_database(args.database, args.backup)
            target = args.database.resolve(strict=True)
        count = apply_migration(target)
        print('Shared foundation ready; quick_check=ok; cards=' + str(count))
    except Exception:
        raise SystemExit('Foundation migration failed; no automatic restore. Inspect the database and backup.') from None


if __name__ == '__main__':
    main()
