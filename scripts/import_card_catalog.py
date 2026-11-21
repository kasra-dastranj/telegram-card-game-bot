"""Preview the approved November catalog, or atomically apply a reviewed plan."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from migrations.import_card_catalog import main


if __name__ == '__main__':
    main()
