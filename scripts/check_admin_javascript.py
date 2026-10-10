"""Check every inline JavaScript block without executing the admin page."""
import re
import subprocess
from pathlib import Path

for filename in ('web/card_management.html','web/custom_card_management.html'):
    page = Path(filename).read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.S | re.I)
    if not scripts:
        raise SystemExit("No admin JavaScript found: "+filename)
    for script in scripts:
        subprocess.run(["node", "--check", "-"], input=script.encode("utf-8"), check=True)
print("Admin JavaScript syntax OK")
