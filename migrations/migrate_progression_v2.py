"""Reviewed additive Phase 2 migration; copy and integrity gate before application."""
import argparse
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from migrations.migrate_card_trait_registry import copy_database
from systems.progression_config import ensure_progression_schema, config_in, validate_config
from systems.shared_foundation import ensure_foundation_schema
from systems.reward_ledger import capacities_in


def apply_migration(database):
    path=Path(database).resolve(strict=True)
    with closing(sqlite3.connect(str(path),timeout=30)) as conn,conn:
        if conn.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('database_integrity_failed')
        conn.execute('BEGIN IMMEDIATE')
        ensure_foundation_schema(conn);ensure_progression_schema(conn)
        _,config=config_in(conn);validate_config(config)
        for user, in conn.execute('SELECT user_id FROM players').fetchall():capacities_in(conn,user,config)
        if conn.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise ValueError('migration_integrity_failed')
    return True


def main():
    parser=argparse.ArgumentParser()
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
    print('Phase 2 schema ready; quick_check=ok; existing users frozen; feature flag unchanged')


if __name__=='__main__':main()
