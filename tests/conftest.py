import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_DB_PATH = Path("/tmp/watchwhat-web-test.db")
TEST_COOKIE_PATH = Path("/tmp/watchwhat-web-cookies-test.json")
os.environ["WATCHWHAT_DB_PATH"] = str(TEST_DB_PATH)
os.environ["WATCHWHAT_SYNC_INLINE"] = "true"
os.environ["WATCHWHAT_DEEPSEEK_API_KEY"] = ""
os.environ["WATCHWHAT_PERSIST_COOKIE_ON_DISK"] = "false"
os.environ["WATCHWHAT_COOKIE_STORE_PATH"] = str(TEST_COOKIE_PATH)


@pytest.fixture(autouse=True)
def clean_db():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    wal = Path(str(TEST_DB_PATH) + "-wal")
    if wal.exists():
        wal.unlink()
    shm = Path(str(TEST_DB_PATH) + "-shm")
    if shm.exists():
        shm.unlink()
    if TEST_COOKIE_PATH.exists():
        TEST_COOKIE_PATH.unlink()
    yield


@pytest.fixture
def client():
    from app.config import clear_settings_cache
    from app.db import init_db, reset_engine
    from app.main import app
    from app.services.cookie_capture import cookie_capture_manager

    clear_settings_cache()
    engine = reset_engine()
    SQLModel.metadata.drop_all(engine)
    init_db()
    cookie_capture_manager.clear_cookie("douban")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session():
    from app.db import get_engine

    with Session(get_engine()) as session:
        yield session
