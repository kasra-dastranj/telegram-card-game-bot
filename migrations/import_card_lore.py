"""Preview/apply/undo only the reviewed biographies and victory text."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from systems.card_lore_import import PACKAGE, ROSTER, load_bundle, preview, apply


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--rollback',action='store_true')
    parser.add_argument('--apply-plan')
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--actor')
    args=parser.parse_args()
    if args.apply_plan and not (args.backup and args.actor):parser.error('--apply-plan requires --backup and --actor')
    protected={args.db.resolve(),Path(str(args.db.resolve())+'-wal'),Path(str(args.db.resolve())+'-shm'),ROSTER.resolve(),
               *(p.resolve() for p in PACKAGE.iterdir() if p.is_file())}
    if args.backup:protected.add(args.backup.resolve())
    if args.report.resolve() in protected or args.report.is_dir() or not args.report.resolve().parent.is_dir():
        parser.error('Report must be a separate file in an existing directory')
    bundle=load_bundle()
    result=apply(args.db,bundle,args.apply_plan,args.backup,args.actor,args.rollback) if args.apply_plan else preview(args.db,bundle,args.rollback)
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','character_count','bio_line_count','active_incoming_lines','active_quotes','changed_biographies','changed_dialog_pools','plan_hash')},ensure_ascii=False))


if __name__=='__main__':main()
