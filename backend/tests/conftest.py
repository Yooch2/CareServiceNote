import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

_BASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://csn:csn@localhost:5433/csn")
TEST_DB_NAME = "csn_test"
os.environ["DATABASE_URL"] = _BASE_URL.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789")
os.environ["AI_PROVIDER"] = "fake"
os.environ["AUDIO_DIR"] = tempfile.mkdtemp(prefix="csn-audio-")
os.environ["STORAGE_KEY"] = "dGVzdC1rZXktbm90LWZvci1wcm9kdWN0aW9uLTAxMjM="  # 테스트 전용 Fernet 키

import psycopg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from psycopg import sql  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


def _ensure_test_database() -> None:
    admin_url = _BASE_URL.replace("postgresql+psycopg://", "postgresql://").rsplit("/", 1)[0]
    with psycopg.connect(admin_url + "/postgres", autocommit=True) as conn:
        found = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if found is None:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB_NAME)))


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    _ensure_test_database()
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    if names:
        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE {names} CASCADE"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other_client() -> Iterator[TestClient]:
    """쿠키가 따로인 두 번째 사용자"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
