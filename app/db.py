from pathlib import Path
from threading import Lock
from typing import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_ENGINE = None
_ENGINE_LOCK = Lock()


def _build_sqlite_url(db_path: str) -> str:
    return f"sqlite:///{db_path}"


def _create_engine():
    settings = get_settings()
    db_file = Path(settings.db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        _build_sqlite_url(settings.db_path),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    return engine


def get_engine():
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = _create_engine()
        return _ENGINE


def reset_engine():
    global _ENGINE
    with _ENGINE_LOCK:
        _ENGINE = _create_engine()
        return _ENGINE


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
