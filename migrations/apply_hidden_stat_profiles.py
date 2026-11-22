"""Preview or apply only the reviewed shared hidden attributes of the roster."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from systems.hidden_stat_profiles import PROFILE_PATH, PACKAGE, load_profile, preview, apply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=PROFILE_PATH)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--apply-plan')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--actor')
    args = parser.parse_args()
    if args.apply_plan and not (args.backup and args.actor):
        parser.error('--apply-plan requires --backup and --actor')
    protected = {args.db.resolve(), Path(str(args.db.resolve())+'-wal'), Path(str(args.db.resolve())+'-shm'),
                 args.profile.resolve(), *(p.resolve() for p in PACKAGE.iterdir() if p.is_file())}
    if args.backup:
        protected.add(args.backup.resolve())
    if args.report.resolve() in protected or args.report.is_dir() or not args.report.resolve().parent.is_dir():
        parser.error('Report must be a separate file in an existing directory')
    profile = load_profile(args.profile)
    result = (apply(args.db, profile, args.apply_plan, args.backup, args.actor) if args.apply_plan
              else preview(args.db, profile))
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    status = 'already_applied' if result['replayed'] else 'applied' if result['applied'] else 'preview'
    print(json.dumps({'status': status, **{k: result[k] for k in ('character_count', 'value_count', 'changed_values', 'plan_hash')},
                      'active_easy_matches': result['active_easy_matches'], 'unscored_dimensions': result['unscored_dimensions'],
                      'unrated_characters': len(result['unrated_characters'])}))


if __name__ == '__main__':
    main()
