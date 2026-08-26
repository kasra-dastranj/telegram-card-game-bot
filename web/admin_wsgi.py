"""Production WSGI entrypoint for the password-protected card admin panel."""

import os

from core.database import DatabaseManager
from web.web_api import WebAPI


database_path = os.environ.get("DATABASE_PATH") or os.environ.get("DB_PATH", "game_bot.db")
app = WebAPI(DatabaseManager(database_path)).app
