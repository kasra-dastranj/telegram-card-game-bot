"""Persist Deck presentation snapshots in the existing report store."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

STAT_NAMES = {'power': 'قدرت', 'speed': 'سرعت', 'iq': 'هوش', 'popularity': 'محبوبیت'}
FORMS = {'normal': '🟢 Normal', 'epic': '🟣 Epic', 'legend': '🟡 Legend', 'rare': '🔵 Rare'}


def isolate(value):
    return f'\u2068{value}\u2069'


def fa(value):
    return str(value).translate(str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹'))


def load_in(conn, fight_id):
    row = conn.execute('SELECT report_json FROM game_match_reports WHERE request_id=?', ('deck:' + fight_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save_in(conn, fight_id, report):
    conn.execute('INSERT OR REPLACE INTO game_match_reports VALUES (?,?,?)',
                 ('deck:' + fight_id, json.dumps(report, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))


def round_snapshot_in(conn, fight_id, players, names, arena, round_num, result, cards):
    report = load_in(conn, fight_id) or {'mode': 'deck', 'players': list(players), 'names': names,
                                      'arena': arena, 'rounds': [], 'completed': False}
    winner = players[0] if result['winner'] == 'challenger' else players[1] if result['winner'] == 'opponent' else None
    record = {'round': round_num, 'winner_id': winner, 'reason': result['reason'],
              'compare_stat': result['compare_stat'], 'cards': {}}
    for uid, role, card in zip(players, ('challenger', 'opponent'), cards):
        record['cards'][str(uid)] = {
            'card_id': getattr(card, 'card_id', None),
            'name': card.name, 'rarity': str(getattr(card.rarity, 'value', card.rarity)),
            'value': result[f'{role}_value'], 'trait_rank': result[f'{role}_trait_rank'],
        }
    report['rounds'] = sorted([item for item in report['rounds'] if item['round'] != round_num] + [record], key=lambda item: item['round'])
    save_in(conn, fight_id, report)
    return report


def backfill_rounds_in(conn, fight_id, report):
    """Recover winners for a match already in progress at rollout; never guess card forms."""
    known = {item['round'] for item in report['rounds']}
    for number, stat, ch_value, op_value, winner in conn.execute(
            'SELECT round_number,challenger_stat,challenger_value,opponent_value,winner FROM round_history WHERE fight_id=? ORDER BY round_number', (fight_id,)):
        if number in known:
            continue
        players = report['players']
        uid = players[0] if winner == 'challenger' else players[1] if winner == 'opponent' else None
        report['rounds'].append({'round': number, 'winner_id': uid, 'reason': 'historical',
                                 'compare_stat': stat, 'cards': {}})
        known.add(number)
    report['rounds'].sort(key=lambda item: item['round'])
    return report


def round_title(report, item):
    winner = item.get('winner_id')
    name = isolate(report['names'][str(winner)]) if winner is not None else 'مساوی'
    return f"برنده راوند {fa(item['round'])}: {name}"


def winner_lines(report):
    rounds = {item['round']: item for item in report['rounds']}
    lines = []
    for number in range(1, 4):
        item = rounds.get(number)
        if item is None:
            lines.append(f'راوند {fa(number)}: برگزار نشد')
        else:
            lines.append(round_title(report, item))
    return '\n'.join(lines)


def finish(db_path, fight_id, players, names, awards, totals=None):
    with closing(sqlite3.connect(db_path, timeout=15)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        report = load_in(conn, fight_id) or {'mode': 'deck', 'players': list(players), 'names': names,
                                          'rounds': [], 'completed': False}
        backfill_rounds_in(conn, fight_id, report)
        report['awards'] = {str(uid): dict(awards[str(uid)]) for uid in players}
        if totals:
            report['totals'] = totals
        # This is the recorded charge, including configurable v2 heart costs.
        for uid, xp, score, hearts in conn.execute(
                'SELECT user_id,xp,score,hearts_lost FROM match_reward_events WHERE request_id=?', ('fight:' + fight_id,)):
            if str(uid) in report['awards']:
                report['awards'][str(uid)].update(xp=xp, score=score, hearts_lost=hearts)
        report['completed'] = True
        conn.execute("UPDATE battle_states SET status='completed' WHERE fight_id=?", (fight_id,))
        save_in(conn, fight_id, report)
        return report


def reward_lines(report):
    lines = []
    for uid in report['players']:
        award = report['awards'][str(uid)]
        line = f"⭐ {isolate(report['names'][str(uid)])}: {isolate('+' + str(award['xp']) + ' XP')}"
        if award.get('hearts_lost'):
            line += f" · {isolate('-' + str(award['hearts_lost']) + ' ❤️')}"
        if award.get('new_level', 1) > award.get('old_level', 1):
            line += f" · Level {award['new_level']} ⬆️"
        lines.append(line)
    return '\n'.join(lines)


def detail_text(report):
    blocks = []
    for item in report['rounds']:
        lines = [round_title(report, item)]
        if item['reason'] == 'historical':
            lines.append('جزئیات کارت‌ها و علت برد این راوند قدیمی ثبت نشده است.')
        else:
            for uid in report['players']:
                card = item['cards'][str(uid)]
                label = f"{card['name']} ({FORMS.get(card['rarity'], card['rarity'])})"
                lines.append(f"{isolate(report['names'][str(uid)])}: {isolate(label)}")
                if item['reason'] == 'stat':
                    lines.append(f"{STAT_NAMES.get(item['compare_stat'], item['compare_stat'])}: {fa(card['value'])}")
                else:
                    lines.append(f"اولویت تریت: {('T' + str(card['trait_rank'])) if card['trait_rank'] else 'بدون تریتِ اولویت‌دار'}")
            if item['winner_id'] is None:
                lines.append('نتیجهٔ مقایسه: مساوی')
            elif item['reason'] == 'trait':
                lines.append('علت برد: تریت با اولویت بالاتر')
            else:
                lines.append(f"علت برد: {STAT_NAMES.get(item['compare_stat'], item['compare_stat'])} بیشتر")
        blocks.append('\n'.join(lines))
    if report.get('totals'):
        lines = ['🧩 امتیاز ساخت دک']
        for uid in report['players']:
            total = report['totals'][str(uid)]
            equation = f"{total['base']} + {total['bonus']} = {total['total']}"
            lines.append(isolate(report['names'][str(uid)]) + ': ' + isolate(equation))
            lines.append('، '.join(total['reasons']) or 'بدون بونس')
        blocks.append('\n'.join(lines))
    if report.get('awards'):
        blocks.append(reward_lines(report))
    return '\n\n'.join(blocks) or 'این بازی پیش از پایان اولین راوند متوقف شد.'
