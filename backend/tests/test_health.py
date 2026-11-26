from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.main import app

client = TestClient(app)


def test_health_ok():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok"}


def test_health_reports_db_down():
    class BrokenSession:
        def execute(self, *_):
            raise OperationalError("SELECT 1", {}, Exception("down"))

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    try:
        res = client.get("/health")
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 503
    assert res.json()["db"] == "unreachable"
