"""Additive Phase 3 schema; private backup/copy, flags unchanged."""
import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from migrations.migrate_card_trait_registry import copy_database
from systems.custom_cards import ensure_custom_schema


def apply_migration(database):
    with closing(sqlite3.connect(str(Path(database).resolve(strict=True)),timeout=30)) as conn,conn:
        if conn.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('database_integrity_failed')
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='reward_ledger'").fetchone():raise ValueError('phase2_schema_required')
        ensure_custom_schema(conn)
        if conn.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('migration_integrity_failed')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--preview-copy',type=Path);mode.add_argument('--apply',action='store_true')
    parser.add_argument('--backup',type=Path)
    args=parser.parse_args()
    if args.apply and not args.backup:parser.error('--apply requires a new --backup')
    if args.preview_copy and args.backup:parser.error('--backup requires --apply')
    if args.preview_copy:target=copy_database(args.database,args.preview_copy)
    else:copy_database(args.database,args.backup);target=args.database
    apply_migration(target)
    print('Phase 3 schema ready; quick_check=ok; flags unchanged; no grants issued')


if __name__=='__main__':main()
