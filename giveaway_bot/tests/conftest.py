"""Изоляция тестов: не подхватываем .env, отдельный SQLite-файл."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

patch("dotenv.load_dotenv", lambda *args, **kwargs: None).start()

_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
TEST_DB_FILE = Path(_TEST_DB_PATH)

os.environ["BOT_TOKEN"] = "123456:pytest-abcdefghijklmnopqrstuvwxyz"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_FILE.resolve().as_posix()}"
os.environ["TWITCH_ENABLED"] = "0"
for _k in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "TWITCH_DISABLED"):
    os.environ.pop(_k, None)

import pytest

from bot.database.database import engine, init_db
from bot.database.models import Base


@pytest.fixture(scope="session", autouse=True)
def _init_db_session():
    init_db()
    yield
    try:
        TEST_DB_FILE.unlink(missing_ok=True)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
