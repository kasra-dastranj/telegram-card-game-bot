"""Load and match authored biography/victory content for cards."""

import json
import re
from pathlib import Path
from typing import Dict, Optional


DEFAULT_CONTENT_PATH = Path(__file__).resolve().parent.parent / "data" / "card_dialogs.json"
GENERATED_CONTENT_PATH = DEFAULT_CONTENT_PATH.with_name("generated_card_content.json")


def normalize_card_name(value: str) -> str:
    """Normalize spacing, punctuation, and case for stable content matching."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def load_card_content(path: Optional[Path] = None) -> Dict[str, dict]:
    """Load the hand-authored base content plus our card-specific additions.

    Passing a path is useful for one-off imports; the normal application path
    deliberately combines both files so newly written content is available to
    imports, the admin panel sync, and battle fallbacks alike.
    """
    paths = [Path(path)] if path else [DEFAULT_CONTENT_PATH, GENERATED_CONTENT_PATH]
    content: Dict[str, dict] = {}
    for content_path in paths:
        if not content_path.is_file():
            continue
        data = json.loads(content_path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            content.update(data)
    return content


def content_for_card(card_name: str, content: Dict[str, dict]) -> Optional[dict]:
    target = normalize_card_name(card_name)
    for source_name, entry in content.items():
        if normalize_card_name(source_name) == target and isinstance(entry, dict):
            return entry
    return None
