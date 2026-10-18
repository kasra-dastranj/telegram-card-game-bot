"""Direction-safe display fragments; never use these values in IDs or storage."""
from telegram.helpers import escape_markdown

_DIRECTION_CONTROLS = str.maketrans('', '', '\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')


def clean(value):
    return str(value).translate(_DIRECTION_CONTROLS)


def isolate(value):
    return '\u2068' + clean(value) + '\u2069'


def ltr(value):
    return '\u2066' + clean(value) + '\u2069'


def markdown_name(value):
    return isolate(escape_markdown(clean(value)))


def ratio(current, total):
    return ltr(f'{current}/{total}')


def signed(value, unit):
    return ltr(f'{int(value):+d} {unit}')
