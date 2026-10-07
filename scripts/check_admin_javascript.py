"""Check every inline JavaScript block without executing the admin page."""
import re
import subprocess
from pathlib import Path

page = Path("web/card_management.html").read_text(encoding="utf-8")
scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", page, re.S | re.I)
if not scripts:
    raise SystemExit("No admin JavaScript found")
for script in scripts:
    subprocess.run(["node", "--check", "-"], input=script.encode("utf-8"), check=True)
print("Admin JavaScript syntax OK")
