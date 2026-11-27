from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Recipient, User
from app.seed import DEMO_LOGIN, DEMO_PASSWORD, DEMO_RECIPIENTS, seed


def test_seed_is_idempotent_and_demo_can_log_in(db: Session, client: TestClient) -> None:
    seed(db)
    seed(db)
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(Recipient)) == len(DEMO_RECIPIENTS)

    res = client.post("/auth/login", json={"login_id": DEMO_LOGIN, "password": DEMO_PASSWORD})
    assert res.status_code == 200
