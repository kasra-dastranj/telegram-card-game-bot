#!/usr/bin/env python3
"""Compatibility CLI for the approved card-manifest importer."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.import_card_manifest import main


if __name__ == "__main__":
    raise SystemExit(main())
