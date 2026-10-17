"""Import pinned pure-Python text shaping sources from previously downloaded wheels.

pip download --no-deps arabic-reshaper==3.0.0 python-bidi==0.4.2 six==1.17.0 -d WHEELS
python scripts/vendor_battle_text.py WHEELS
"""
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    'arabic_reshaper-3.0.0-py3-none-any.whl': '3f71d5034bb694204a239a6f1ebcf323ac3c5b059de02259235e2016a1a5e2dc',
    'python_bidi-0.4.2-py2.py3-none-any.whl': '50eef6f6a0bbdd685f9e8c207f3c9050f5b578d0a46e37c76a9c4baea2cc2e13',
    'six-1.17.0-py2.py3-none-any.whl': '4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274',
}


def vendor(wheels):
    target = ROOT / 'bot/_vendor'
    target.mkdir(exist_ok=True)
    (target / '__init__.py').write_text('"""Pinned text rendering dependencies; see THIRD_PARTY.md."""\n', encoding='utf-8')
    licenses = {}
    for name, digest in PACKAGES.items():
        raw = (wheels / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('wheel checksum mismatch: ' + name)
        with zipfile.ZipFile(wheels / name) as archive:
            for member in archive.namelist():
                if member.endswith('.py') and (member.startswith(('bidi/', 'arabic_reshaper/')) or member == 'six.py'):
                    path = target / member
                    path.parent.mkdir(exist_ok=True)
                    text = archive.read(member).decode('utf-8')
                    if member.startswith('bidi/'):
                        text = text.replace('import six\n', 'from .. import six\n')
                    path.write_text(text, encoding='utf-8')
                elif member.rsplit('/', 1)[-1] in ('LICENSE', 'COPYING', 'COPYING.LESSER', 'AUTHORS.rst'):
                    licenses[member] = archive.read(member).decode('utf-8')
    # Keep complete upstream notices in the Python-only deployment artifact, too.
    (target / '_licenses.py').write_text('"""Complete upstream licenses, retained for redistribution."""\nLICENSES = '
                                       + repr(licenses) + '\n', encoding='utf-8')


if __name__ == '__main__':
    vendor(Path(sys.argv[1]))
