"""Transactional private notification outbox; never grants or replays prizes."""
import json
import sqlite3
import time
from contextlib import closing

PREFIX='level-notice:'


def queue_in(conn,user,level,rewards=None,unlocks=None):
    conn.execute('INSERT OR IGNORE INTO foundation_settings(key,value_json) VALUES(?,?)',
                 (PREFIX+str(user)+':'+str(level),json.dumps({
                     'user_id':user,'level':level,'rewards':rewards or {},
                     'unlocks':unlocks or [],'sent':False,'next_attempt':0})))


def pending(db,limit=10):
    with closing(sqlite3.connect(db.db_path,timeout=15)) as conn:
        rows=conn.execute("SELECT key,value_json FROM foundation_settings WHERE key LIKE ? AND json_extract(value_json,'$.sent')=0 AND json_extract(value_json,'$.next_attempt')<=? ORDER BY rowid LIMIT ?",
                          (PREFIX+'%',time.time(),limit)).fetchall()
        return [(key,json.loads(value)) for key,value in rows]


def finish(db,key,sent):
    with closing(sqlite3.connect(db.db_path,timeout=15)) as conn:
        with conn:
            conn.execute("UPDATE foundation_settings SET value_json=json_set(value_json,'$.sent',json(?),'$.next_attempt',?) WHERE key=?",
                         (json.dumps(bool(sent)),time.time()+1800,key))
