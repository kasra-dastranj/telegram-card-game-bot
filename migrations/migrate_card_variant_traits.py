"""Owner migration: nullable form overrides, preserving all legacy trait values."""
import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from migrations.migrate_card_trait_registry import copy_database
from systems.card_trait_registry import ensure_trait_registry_schema, ensure_variant_traits_schema


def apply_migration(database):
    with closing(sqlite3.connect(str(database), timeout=30)) as conn:
        if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise RuntimeError('SQLite integrity check failed')
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='card_mode_metadata' AND type='table'").fetchone():
            raise RuntimeError('Expected card metadata table is missing')
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            ensure_variant_traits_schema(conn)
            ensure_trait_registry_schema(conn)
            if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('Migration integrity check failed')


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
        apply_migration(target)
        print('Independent form traits ready; legacy values preserved; SQLite quick_check=ok')
    except Exception:
        raise SystemExit('Form trait migration failed; no automatic restore. Owner must inspect the backup and database.') from None


if __name__ == '__main__':
    main()
