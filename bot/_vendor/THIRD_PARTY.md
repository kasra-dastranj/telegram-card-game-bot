# Text shaping dependencies

These pinned, pure-Python sources keep bitmap Persian text consistent on Windows and Python 3.9/Linux without changing the production venv. No external executable, API, or network request is used for text shaping.

| Component | Upstream | License |
| --- | --- | --- |
| arabic-reshaper 3.0.0 | https://pypi.org/project/arabic-reshaper/3.0.0/ | MIT |
| python-bidi 0.4.2 | https://pypi.org/project/python-bidi/0.4.2/ | LGPL-3.0-or-later |
| six 1.17.0 | https://pypi.org/project/six/1.17.0/ | MIT |

Full upstream licenses (including GPL/LGPL and author notices) are retained in `_licenses.py`, so the Python-only runtime artifact carries them too. Upstream source copyright notices remain in the source files. python-bidi's `import six` statements alone were changed to `from .. import six` to isolate the vendored copy; all shaping/ordering algorithms are unchanged. These library modules remain separate and replaceable; modified library source is supplied in this repository and release artifact under the upstream license.

Reproduce the import with `scripts/vendor_battle_text.py` after downloading the three pinned wheels with `pip download --no-deps`. The script checks SHA-256 before copying any source. Exact wheel names and hashes are in that script. No package installation or secret is required on the production server. The reusable font is separately licensed under `frontend/game/public/fonts/Vazirmatn-OFL.txt`, also included inside `bot/battle_visual_assets.py`'s resource archive.
