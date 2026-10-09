"""Offline owner/admin tool: inspect, validate and edit persisted economy settings."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from systems.progression_config import config_in, save_config_in, validate_config
from systems.progression_missions import save_mission_in


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--actor',default=None)
    actions=parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--export',type=Path)
    actions.add_argument('--import-config',type=Path)
    actions.add_argument('--mission',type=Path)
    actions.add_argument('--legend-tier',nargs=2,metavar=('CARD_ID','A_OR_B'))
    actions.add_argument('--skin-price',nargs=2,metavar=('SKIN_ID','PRICE'))
    actions.add_argument('--rare-supply',nargs=2,metavar=('CARD_ID','TOTAL_SUPPLY'))
    actions.add_argument('--flag',choices=('on','off'))
    actions.add_argument('--audit',action='store_true')
    args=parser.parse_args()
    path=args.database.resolve(strict=True)
    if (args.import_config or args.mission or args.legend_tier or args.skin_price or args.rare_supply or args.flag) and not args.actor:
        parser.error('mutations require --actor')
    with closing(sqlite3.connect(str(path),timeout=30)) as conn,conn:
        conn.execute('BEGIN IMMEDIATE')
        audit=None
        if args.export:
            version,value=config_in(conn)
            with args.export.open('x',encoding='utf8') as output:json.dump(value,output,ensure_ascii=False,indent=2)
            print('exported version',version)
        elif args.import_config:
            value=json.loads(args.import_config.read_text(encoding='utf-8-sig'))
            print('saved version',save_config_in(conn,value,args.actor))
        elif args.mission:
            value=json.loads(args.mission.read_text(encoding='utf-8-sig'))
            print('mission version',save_mission_in(conn,value,args.actor))
        elif args.legend_tier:
            card,tier=args.legend_tier
            if tier not in ('A','B') or not conn.execute("SELECT 1 FROM cards WHERE card_id=? AND origin='official'",(card,)).fetchone():raise ValueError('invalid_character_recipe')
            old=conn.execute('SELECT legend_recipe_tier FROM economy_character_rules WHERE card_id=?',(card,)).fetchone()
            audit=('legend_tier',{'card_id':card,'before':old[0] if old else None,'after':tier})
            conn.execute('INSERT INTO economy_character_rules VALUES(?,?) ON CONFLICT(card_id) DO UPDATE SET legend_recipe_tier=excluded.legend_recipe_tier',(card,tier))
            conn.execute('INSERT INTO economy_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('recipe_audit:'+card,json.dumps({'tier':tier,'actor':args.actor})))
            # Recipe edits invalidate outstanding quotes/previews by advancing config version.
            save_config_in(conn,config_in(conn)[1],args.actor)
            print('recipe saved',card,tier)
        elif args.skin_price:
            skin,price=args.skin_price
            price=int(price)
            if price<0:raise ValueError('invalid_skin_price')
            old=conn.execute('SELECT price FROM skins WHERE skin_id=?',(skin,)).fetchone()
            audit=('skin_price',{'skin_id':skin,'before':old[0] if old else None,'after':price})
            if conn.execute('UPDATE skins SET price=? WHERE skin_id=?',(price,skin)).rowcount!=1:raise ValueError('skin_not_found')
            save_config_in(conn,config_in(conn)[1],args.actor)
            print('skin price saved')
        elif args.rare_supply:
            card,supply=args.rare_supply
            supply=int(supply)
            old=conn.execute("SELECT r.limited_quantity,r.total_issued FROM rare_cards_info r JOIN cards c USING(card_id) WHERE r.card_id=? AND c.origin='official' AND c.rarity='rare'",(card,)).fetchone()
            if not old or supply<old[1] or supply<0:raise ValueError('invalid_rare_supply')
            conn.execute('UPDATE rare_cards_info SET limited_quantity=? WHERE card_id=?',(supply,card))
            audit=('rare_supply',{'card_id':card,'before':old[0],'after':supply,'issued':old[1]})
            save_config_in(conn,config_in(conn)[1],args.actor)
            print('rare supply saved')
        elif args.flag:
            version,value=config_in(conn);validate_config(value)
            old=conn.execute("SELECT value_json FROM foundation_settings WHERE key='progression_v2_enabled'").fetchone()
            audit=('flag',{'before':json.loads(old[0]),'after':args.flag=='on','config_version':version})
            conn.execute("UPDATE foundation_settings SET value_json=? WHERE key='progression_v2_enabled'",(json.dumps(args.flag=='on'),))
            conn.execute('INSERT INTO economy_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('flag_audit',json.dumps({'actor':args.actor,'enabled':args.flag=='on','config_version':version})))
            print('progression_v2_enabled',args.flag)
        elif args.audit:
            for version,actor,created in conn.execute('SELECT version,actor,created_at FROM economy_config_versions ORDER BY version'):
                print(version,actor,created)
            for action,details,actor,created in conn.execute('SELECT action,details_json,actor,created_at FROM economy_admin_audit ORDER BY id'):
                print(action,details,actor,created)
        if audit:
            conn.execute('INSERT INTO economy_admin_audit(action,details_json,actor,created_at) VALUES(?,?,?,?)',(audit[0],json.dumps(audit[1]),args.actor,datetime.now(timezone.utc).isoformat()))


if __name__=='__main__':main()
