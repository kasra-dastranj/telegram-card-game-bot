"""Resolve uploaded sticker artwork without borrowing a different card form."""
import re
from pathlib import Path


def sticker_path(card, *, root=None, include_legacy=True):
    if not card or getattr(card, 'origin', 'official') == 'custom':
        return None
    name = str(getattr(card, 'name', '') or '').strip()
    if not name:
        return None
    normalized = name.upper().replace('-', '_')
    stems = [re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value).strip(' ._')
             for value in (normalized.replace(' ', '_'), normalized, normalized.replace(' ', ''))]
    rarity = str(getattr(getattr(card, 'rarity', ''), 'value', getattr(card, 'rarity', ''))).upper()
    root = Path(root) if root is not None else Path.cwd()
    directories = (root / 'assets' / 'stickers', root / 'stickers')
    for form_specific in (True, False) if include_legacy else (True,):
        # Old shared stickers must not override newly selected form artwork.
        if not form_specific and getattr(card, 'image_path', ''):
            image = Path(card.image_path)
            if (image if image.is_absolute() else root / image).is_file():
                return None
        for directory in directories:
            for stem in dict.fromkeys(stems):
                if not stem or form_specific and not rarity:
                    continue
                filename = f'{stem}_{rarity}' if form_specific else stem
                for suffix in ('.webp', ' (2).webp'):
                    path = directory / (filename + suffix)
                    if path.is_file():
                        return str(path)
    return None
