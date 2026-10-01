"""Create a consistent SQLite backup without stopping the game services."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.destination.exists():
        parser.error("destination already exists")
    with sqlite3.connect(args.source.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(str(args.destination)) as destination:
            source.backup(destination)
    args.destination.chmod(0o600)
    print(args.destination)


if __name__ == "__main__":
    main()
