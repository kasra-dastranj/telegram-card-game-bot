"""Rebuild the native blank store backdrop; custom replacements can use the manifest."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot.shop_visuals import template_png

if __name__ == '__main__':
    destination = ROOT/'assets/battle_visuals/shop-template-v1.png'
    destination.write_bytes(template_png())
    print(destination.relative_to(ROOT))
