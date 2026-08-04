#!/usr/bin/env python3
"""Compatibility launcher for the current TelBattle card manager."""

try:
    from .web_api import main
except ImportError:  # Direct execution: python web/web_admin_panel_phase2.py
    from web_api import main


if __name__ == "__main__":
    main()
