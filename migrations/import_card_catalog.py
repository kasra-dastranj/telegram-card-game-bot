"""Owner-run catalog preview/apply CLI; importing this module never mutates data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from systems.card_catalog_import import PACKAGE, load_catalog, preview, apply


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=PACKAGE / 'telbattle_cards.json')
    parser.add_argument('--csv', type=Path, default=PACKAGE / 'telbattle_cards_flat.csv')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--apply-plan')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--actor')
    args = parser.parse_args()
    if args.apply_plan and not (args.backup and args.actor):
        parser.error('--apply-plan requires --backup and --actor')
    if args.report.resolve() in {args.db.resolve(), args.source.resolve(), args.csv.resolve()}:
        parser.error('Report path must not overwrite input or game data')
    catalog = load_catalog(args.source, args.csv)
    result = (apply(args.db, catalog, args.apply_plan, args.backup, args.actor) if args.apply_plan
              else preview(args.db, catalog))
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('counts', 'created', 'updated', 'plan_hash', 'replayed')}))
    print('Removed:', len(result['removed']), '| Applied:', result.get('applied', False))


if __name__ == '__main__':
    main()
