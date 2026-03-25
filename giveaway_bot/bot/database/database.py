from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from bot.config import DATABASE_URL
from bot.database.models import Base

# Параметры для SQLite (многопоточность)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_TWITCH_LINK_ALTER = [
    "ALTER TABLE twitch_links ADD COLUMN twitch_user_id VARCHAR(32)",
    "ALTER TABLE twitch_links ADD COLUMN access_token TEXT",
    "ALTER TABLE twitch_links ADD COLUMN refresh_token TEXT",
    "ALTER TABLE twitch_links ADD COLUMN token_expires_at TIMESTAMP",
]


def _migrate_twitch_link_columns():
    """Добавляет колонки OAuth к существующей таблице twitch_links (без Alembic)."""
    try:
        insp = inspect(engine)
        if not insp.has_table("twitch_links"):
            return
        existing = {c["name"] for c in insp.get_columns("twitch_links")}
    except Exception:
        return
    for stmt in _TWITCH_LINK_ALTER:
        col = stmt.split("ADD COLUMN ")[1].split()[0]
        if col in existing:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception:
            pass


def init_db():
    """Создание всех таблиц"""
    Base.metadata.create_all(bind=engine)
    _migrate_twitch_link_columns()
    print("✅ База данных инициализирована")


@contextmanager
def get_db() -> Session:
    """Контекстный менеджер для сессии БД"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


def get_session() -> Session:
    """Получить новую сессию БД"""
    return SessionLocal()
