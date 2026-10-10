"""Explicit owner cutover, preview on a private SQLite copy before live application."""
import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from migrations.migrate_card_trait_registry import copy_database
from systems.progression_rollout import activate_in


def apply_activation(database, actor, legend_default='B', now=None):
    path = Path(database).resolve(strict=True)
    with closing(sqlite3.connect(str(path), timeout=30)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise ValueError('database_integrity_failed')
        violations_before = conn.execute('PRAGMA foreign_key_check').fetchall()
        receipt = activate_in(conn, actor, legend_default, now)
        if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)] or conn.execute('PRAGMA foreign_key_check').fetchall() != violations_before:
            raise ValueError('rollout_integrity_failed')
        receipt['existing_foreign_key_violations'] = len(violations_before)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview-copy', type=Path)
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--actor', required=True)
    parser.add_argument('--legend-default', choices=['B'], default='B')
    args = parser.parse_args()
    if args.apply and not args.backup:
        parser.error('--apply requires a new --backup')
    if args.preview_copy and args.backup:
        parser.error('--backup requires --apply')
    if args.preview_copy:
        target = copy_database(args.database, args.preview_copy)
    else:
        copy_database(args.database, args.backup)
        target = args.database
    receipt = apply_activation(target, args.actor, args.legend_default)
    print(json.dumps({'preview': bool(args.preview_copy), **receipt}, sort_keys=True))


if __name__ == '__main__':
    main()
