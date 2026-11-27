from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assignment, Consent, GuardianLink, Recipient, User, VisitRecord
from app.seed import DEMO_PASSWORD, DEMO_RECIPIENTS, DEMO_USERS, GUARDIAN_OF, seed


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


def test_seed_history_tells_the_demo_story(db: Session, client: TestClient) -> None:
    seed(db)
    seed(db)  # 이력은 한 번만
    kim = db.scalar(select(Recipient).where(Recipient.name == GUARDIAN_OF))
    assert kim is not None
    assert db.scalar(select(func.count()).select_from(VisitRecord)) == 4

    client.post("/auth/login", json={"login_id": "manager", "password": DEMO_PASSWORD})
    alerts = client.get(f"/recipients/{kim.id}/alerts").json()
    assert sorted((a["kind"], a["key"]) for a in alerts) == [
        ("meal_drop", "meal"),
        ("repeated_discomfort", "knee"),
    ]
    handover = client.get(f"/recipients/{kim.id}/handover", params={"days": 14}).json()
    assert [f["content"] for f in handover["open_followups"]] == ["식사량 다시 확인"]
    assert handover["completion"] == {"due": 3, "checked": 2}
    assert len(client.get("/org/reviews").json()) == 2  # 최근 두 방문은 확인 대기

    client.post("/auth/login", json={"login_id": "family", "password": DEMO_PASSWORD})
    home = client.get("/guardian/home").json()
    # 보호자 열람 범위(말씀·다음 확인)라 관찰 문장은 빠진다
    assert [s for r in home["records"] for s in r["summary"]] == [
        "어르신께서 요즘 기운이 없다고 말씀하셨습니다."
    ]
    assert [n["message"] for n in home["notices"]] == [
        "무릎 통증 때문에 이번 주 금요일 정형외과 진료를 예약해 두었습니다."
    ]
