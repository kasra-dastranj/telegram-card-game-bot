"""Editable Easy content, stored in the existing settings table; no executable formulas."""
import copy
import json
import re
from datetime import datetime, timezone

CATALOG_KEY = 'easy_question_catalog_v1'
CORE_STATS = {'power': 'قدرت', 'speed': 'سرعت', 'iq': 'هوش', 'popularity': 'محبوبیت'}
HIDDEN_STATS = {'funny': 'بامزگی', 'scary': 'ترسناکی', 'charisma': 'کاریزما',
                'cute': 'کیوتی', 'evil': 'شرارت', 'leadership': 'رهبری',
                'survival': 'بقا / سوروایور بودن', 'management': 'مدیریت'}
KEY_PATTERN = r'[a-z][a-z0-9_]{0,39}'
DEFAULT_QUESTIONS = [
    {'id': key, 'text': text, 'attribute': stat}
    for key, text, stat in (
        ('smart', 'باهوش‌ترین شخصیت کیست؟', 'iq'), ('strong', 'قوی‌ترین شخصیت کیست؟', 'power'),
        ('fast', 'سریع‌ترین شخصیت کیست؟', 'speed'), ('popular', 'محبوب‌ترین شخصیت کیست؟', 'popularity'),
        ('funny', 'بامزه‌ترین شخصیت کیست؟', 'funny'), ('scary', 'ترسناک‌ترین شخصیت کیست؟', 'scary'),
        ('charismatic', 'کاریزماتیک‌ترین شخصیت کیست؟', 'charisma'), ('cute', 'کیوت‌ترین شخصیت کیست؟', 'cute'),
        ('evil', 'شرورترین شخصیت کیست؟', 'evil'), ('leader', 'بهترین رهبر کیست؟', 'leadership'))]


class CatalogConflict(ValueError):
    pass


def default_catalog():
    questions = [dict(id=q['id'], text=q['text'], formula=q['attribute'], enabled=True,
                      filter='none', filter_value='') for q in DEFAULT_QUESTIONS]
    questions += [dict(id='trait_iq', text='باهوش‌ترین شخصیت با ویژگی {trait} کیست؟',
                       formula='iq', enabled=True, filter='trait', filter_value=''),
                  dict(id='series_popularity', text='محبوب‌ترین شخصیت از مجموعه {series} کیست؟',
                       formula='popularity', enabled=True, filter='series', filter_value='')]
    return {'revision': 0, 'stats': {**CORE_STATS, **HIDDEN_STATS}, 'questions': questions}


def formula_terms(expression, stats):
    """Only a bounded sequence of registered names joined with + or -. Never eval."""
    if not isinstance(expression, str) or len(expression) > 700:
        raise ValueError('فرمول باید نام ویژگی‌ها با جمع یا تفریق باشد.')
    compact = re.sub(r'\s+', '', expression)
    if not re.fullmatch(KEY_PATTERN + r'(?:[+-]' + KEY_PATTERN + r')*', compact):
        raise ValueError('در فرمول فقط نام ویژگی و علامت + یا - مجاز است.')
    terms = [(1 if sign != '-' else -1, key) for sign, key in re.findall(r'([+-]?)(' + KEY_PATTERN + ')', compact)]
    if len(terms) > 16 or any(key not in stats for _, key in terms):
        raise ValueError('فرمول باید حداکثر ۱۶ بخش و فقط ویژگی‌های تعریف‌شده داشته باشد.')
    return terms


def validate_catalog(data):
    if not isinstance(data, dict) or type(data.get('revision')) is not int or data['revision'] < 0:
        raise ValueError('نسخهٔ فهرست نامعتبر است؛ صفحه را دوباره بارگذاری کن.')
    stats, questions = data.get('stats'), data.get('questions')
    if not isinstance(stats, dict) or not CORE_STATS.keys() <= stats.keys() or not isinstance(questions, list):
        raise ValueError('فهرست ویژگی‌ها یا سؤال‌ها نامعتبر است.')
    clean_stats = {}
    for key, label in stats.items():
        if not re.fullmatch(KEY_PATTERN, key) or not isinstance(label, str) or not 1 <= len(label.strip()) <= 70:
            raise ValueError('ویژگی باید شناسهٔ انگلیسی ساده و نام نمایشی داشته باشد.')
        clean_stats[key] = label.strip()
    clean_questions, seen = [], set()
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError('ساختار سؤال نامعتبر است.')
        key, text = item.get('id'), item.get('text')
        if not isinstance(key, str) or not re.fullmatch(KEY_PATTERN, key) or key in seen:
            raise ValueError('شناسهٔ سؤال تکراری یا نامعتبر است.')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 350 or type(item.get('enabled')) is not bool:
            raise ValueError('متن سؤال باید ۱ تا ۳۵۰ نویسه باشد.')
        mode, value = item.get('filter', 'none'), item.get('filter_value', '')
        if mode not in ('none', 'trait', 'series') or not isinstance(value, str) or len(value.strip()) > 100:
            raise ValueError('شرط سؤال نامعتبر است.')
        if ('{trait}' in text and mode != 'trait') or ('{series}' in text and mode != 'series'):
            raise ValueError('جای‌نگهدار متن باید با شرط تریت یا مجموعه هماهنگ باشد.')
        if mode != 'none' and not value.strip() and '{' + mode + '}' not in text:
            raise ValueError('برای شرط خودکار، {trait} یا {series} را در متن سؤال بنویس.')
        terms = formula_terms(item.get('formula'), clean_stats)
        formula = ' '.join((('' if i == 0 else '+ ' if sign == 1 else '- ') + stat)
                           for i, (sign, stat) in enumerate(terms))
        clean_questions.append(dict(id=key, text=text.strip(), formula=formula,
                                    enabled=item['enabled'], filter=mode, filter_value=value.strip()))
        seen.add(key)
    if not any(q['enabled'] and q['filter'] == 'none' for q in clean_questions):
        raise ValueError('حداقل یک سؤال فعال بدون شرط لازم است تا بازی همیشه سؤال داشته باشد.')
    return dict(revision=data['revision'], stats=clean_stats, questions=clean_questions)


def catalog_in(conn):
    row = conn.execute('SELECT value_json FROM foundation_settings WHERE key=?', (CATALOG_KEY,)).fetchone()
    return json.loads(row[0]) if row else default_catalog()


def save_catalog_in(conn, data, actor):
    clean = validate_catalog(data)
    current = catalog_in(conn)
    if current['revision'] != clean['revision']:
        raise CatalogConflict('فهرست در صفحهٔ دیگری تغییر کرده؛ دوباره بارگذاری کن.')
    clean.update(revision=clean['revision'] + 1, actor=actor, updated_at=datetime.now(timezone.utc).isoformat())
    # One previous copy for review/recovery; current games carry their own immutable copy.
    conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES(?,?)',
                 (CATALOG_KEY + '_previous', json.dumps(current, ensure_ascii=False)))
    conn.execute('INSERT OR REPLACE INTO foundation_settings VALUES(?,?)',
                 (CATALOG_KEY, json.dumps(clean, ensure_ascii=False)))
    return clean


def question_pool(catalog, traits, series):
    pool = []
    for template in catalog['questions']:
        if not template['enabled']:
            continue
        mode = template['filter']
        if mode == 'none':
            pool.append(copy.deepcopy(template))
            continue
        available = traits if mode == 'trait' else series
        wanted = template['filter_value'].casefold()
        for key, label in sorted(available.items()):
            if wanted and key != wanted:
                continue
            pool.append({**template, 'id': template['id'] + ':' + key, mode: label,
                         'text': template['text'].replace('{' + mode + '}', '\u2068' + label + '\u2069')})
    return pool


def evaluate_card(modes, card, question):
    """Trait match is the first comparison key; the signed formula is the second."""
    metadata = modes.metadata_for_card(card)
    trait, series = question.get('trait'), question.get('series')
    eligible = (not trait or trait.casefold() in {str(t).strip().casefold() for t in metadata.get('traits', [])})
    eligible = eligible and (not series or series.casefold() == str(metadata.get('series') or '').strip().casefold())
    expression = question.get('formula', question.get('attribute', 'iq'))
    # Names were validated by the editor; legacy in-progress questions have one attribute.
    names = set(re.findall(KEY_PATTERN, expression))
    terms = formula_terms(expression, names)
    values = {key: modes._hidden_stat_value(card, key) for _, key in terms}
    return {'card_id': card.card_id, 'card_name': card.name, 'eligible': bool(eligible),
            'hidden_value': sum(sign * values[key] for sign, key in terms),
            'formula': expression, 'components': values}
