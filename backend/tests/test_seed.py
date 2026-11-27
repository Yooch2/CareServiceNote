from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, Consent, GuardianLink, Recipient, User
from app.seed import DEMO_PASSWORD, DEMO_RECIPIENTS, DEMO_USERS, seed


def test_seed_is_idempotent_and_demo_accounts_work(db: Session, client: TestClient) -> None:
    seed(db)
    seed(db)
    assert db.scalar(select(func.count()).select_from(User)) == len(DEMO_USERS)
    assert db.scalar(select(func.count()).select_from(Recipient)) == len(DEMO_RECIPIENTS)
    assert db.scalar(select(func.count()).select_from(Assignment)) == len(DEMO_RECIPIENTS)
    # 건강정보 동의 3 + 보호자 공유 1
    assert db.scalar(select(func.count()).select_from(Consent)) == len(DEMO_RECIPIENTS) + 1
    assert db.scalar(select(func.count()).select_from(GuardianLink)) == 1

    for login_id, role, _ in DEMO_USERS:
        res = client.post("/auth/login", json={"login_id": login_id, "password": DEMO_PASSWORD})
        assert res.status_code == 200
        assert res.json()["role"] == role
    assert client.get("/guardian/home").json()["recipient_name"] == "김순자(가상)"
