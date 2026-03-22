from sqlalchemy import create_engine
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


def init_db():
    """Создание всех таблиц"""
    Base.metadata.create_all(bind=engine)
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
