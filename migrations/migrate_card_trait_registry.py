"""Owner-reviewed additive migration. Preview on a SQLite backup before --apply."""
import argparse
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from systems.card_trait_registry import ensure_trait_registry_schema


def copy_database(source, destination):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    # Exclusive creation prevents overwriting a backup or an existing database.
    descriptor = os.open(str(destination), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        with closing(sqlite3.connect(str(destination))) as copy:
            original.backup(copy)
            if copy.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('SQLite backup integrity check failed')
    return destination


def apply_migration(database):
    with closing(sqlite3.connect(str(database), timeout=30)) as conn:
        if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise RuntimeError('SQLite integrity check failed')
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='card_mode_metadata' AND type='table'").fetchone():
            raise RuntimeError('Expected TelBattle card metadata table is missing')
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            ensure_trait_registry_schema(conn)
            if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('Migration integrity check failed')
        return conn.execute('SELECT COUNT(*) FROM card_trait_registry').fetchone()[0]


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
        print('Trait registry ready; SQLite quick_check=ok; registered traits=' + str(count))
    except Exception:
        raise SystemExit('Trait migration failed; no automatic restore. Owner must inspect the backup and database.') from None


if __name__ == '__main__':
    main()
