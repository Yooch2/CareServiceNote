"""4단계: 변화 알림 규칙, 긴급 우려, 센터 인박스, 추이"""

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import evaluate_alerts
from app.models import Alert, Recipient, VisitRecord
from tests.helpers import (
    add_recipient,
    colleague,
    make_confirmed,
    new_org,
    process_all,
    put_audio,
    signup,
    signup_center,
)

D0 = date(2026, 11, 10)


def _recipient(db: Session) -> uuid.UUID:
    r = Recipient(name="가상수급자", org_id=new_org(db).id)
    db.add(r)
    db.commit()
    return r.id


def _visit(db: Session, rid: uuid.UUID, day: int, items=(), **kw) -> VisitRecord:  # noqa: ANN001
    record = make_confirmed(
        db, list(items), recipient_id=rid, visited_on=D0 + timedelta(days=day), **kw
    )
    evaluate_alerts(db, record)
    db.commit()
    return record


def _open(db: Session, rid: uuid.UUID) -> list[Alert]:
    db.expire_all()
    return list(db.scalars(select(Alert).where(Alert.recipient_id == rid, Alert.status == "open")))


KNEE = [("remark", "무릎이 불편하다고 하심")]


def test_same_part_twice_within_7_days(db: Session) -> None:
    rid = _recipient(db)
    first = _visit(db, rid, 0, KNEE, parts={0: "knee"})
    assert _open(db, rid) == []
    second = _visit(db, rid, 7, KNEE, parts={0: "knee"})
    [alert] = _open(db, rid)
    assert (alert.kind, alert.key) == ("repeated_discomfort", "knee")
    assert [e["record_id"] for e in alert.evidence] == [str(first.id), str(second.id)]
    assert all(e["item_id"] for e in alert.evidence)


def test_no_alert_beyond_window_other_part_or_uncertain(db: Session) -> None:
    rid = _recipient(db)
    _visit(db, rid, 0, KNEE, parts={0: "knee"})
    _visit(db, rid, 8, KNEE, parts={0: "knee"})  # 8일 차이
    _visit(db, rid, 9, [("remark", "허리가 아프다고 하심")], parts={0: "back"})
    _visit(db, rid, 10, KNEE, parts={0: "knee"}, uncertain={0})  # 발화자 미확인
    two_in_one = [("remark", "무릎이 쑤심"), ("observation", "무릎을 문지르심")]
    _visit(db, _recipient(db), 0, two_in_one, parts={0: "knee", 1: "knee"})  # 한 방문 안
    assert _open(db, rid) == []


def test_open_alert_merges_and_resolved_starts_new(db: Session) -> None:
    rid = _recipient(db)
    _visit(db, rid, 0, KNEE, parts={0: "knee"})
    _visit(db, rid, 2, KNEE, parts={0: "knee"})
    _visit(db, rid, 4, KNEE, parts={0: "knee"})
    [alert] = _open(db, rid)
    assert len(alert.evidence) == 3  # 같은 사유는 하나로, 근거만 늘어남

    alert.status = "resolved"
    db.commit()
    _visit(db, rid, 6, KNEE, parts={0: "knee"})
    [fresh] = _open(db, rid)
    assert fresh.id != alert.id


def test_meal_drop(db: Session) -> None:
    rid = _recipient(db)
    _visit(db, rid, 0, meal_level=4)
    _visit(db, rid, 2)  # 식사 언급 없는 방문은 비교하지 않음
    _visit(db, rid, 3, meal_level=3)  # 한 단계는 알림 없음
    assert _open(db, rid) == []
    _visit(db, rid, 5, meal_level=1)
    [alert] = _open(db, rid)
    assert (alert.kind, alert.key) == ("meal_drop", "meal")
    assert [e["text"] for e in alert.evidence] == ["식사량: 대부분", "식사량: 조금"]


def test_meal_drop_found_when_earlier_visit_confirmed_late(db: Session) -> None:
    rid = _recipient(db)
    _visit(db, rid, 5, meal_level=1)
    _visit(db, rid, 2, meal_level=4)  # 앞 방문이 나중에 확정됨
    assert [a.kind for a in _open(db, rid)] == ["meal_drop"]


def test_confirm_creates_alert_and_state_is_saved(client: TestClient, db: Session) -> None:
    signup(client)
    rid = add_recipient(client)["id"]
    make_confirmed(
        db, KNEE, recipient_id=uuid.UUID(rid), visited_on=date(2026, 11, 25), parts={0: "knee"}
    )
    record_id = str(uuid.uuid4())
    put_audio(client, record_id, rid)  # 방문일 2026-11-27
    process_all()
    draft = client.get(f"/records/{record_id}").json()["draft"]
    assert draft["state"]["meal_level"] == 2
    assert draft["items"][0]["body_part"] == "knee"

    body = {
        "items": [
            {
                "draft_index": i,
                "category": it["category"],
                "content": it["content"],
                "evidence": it["evidence"],
                "risk_tag": it["risk_tag"],
                "body_part": it["body_part"],
            }
            for i, it in enumerate(draft["items"])
        ],
        "meal_level": 2,
        "mood": "neutral",
    }
    confirmed = client.post(f"/records/{record_id}/confirm", json=body).json()
    assert (confirmed["meal_level"], confirmed["mood"]) == (2, "neutral")
    assert confirmed["items"][0]["body_part"] == "knee"
    [alert] = client.get(f"/recipients/{rid}/alerts").json()
    assert alert["kind"] == "repeated_discomfort" and len(alert["evidence"]) == 2

    trend = client.get(f"/recipients/{rid}/trends", params={"days": 90}).json()
    assert [(t["meal_level"], t["mood"]) for t in trend] == [(2, "neutral")]


def test_concern_and_inbox(client: TestClient, other_client: TestClient) -> None:
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    client.post(
        f"/recipients/{rid}/consents", json={"kind": "health_record", "granted_on": "2026-11-01"}
    )
    colleague(client, other_client, assign_to=rid)

    assert other_client.post(f"/recipients/{rid}/concerns", json={"note": "  "}).status_code == 422
    made = other_client.post(f"/recipients/{rid}/concerns", json={"note": "숨이 차 보이심"})
    assert made.status_code == 201
    other_client.post(f"/recipients/{rid}/concerns", json={"note": "식사를 거르심"})

    inbox = client.get("/org/alerts").json()
    assert [a["note"] for a in inbox] == [
        "숨이 차 보이심",
        "식사를 거르심",
    ]  # 긴급 우려는 합치지 않음
    assert inbox[0]["recipient_name"] == "가상수급자" and inbox[0]["created_by_name"] == "동료"

    url = f"/org/alerts/{inbox[0]['id']}/resolve"
    done = client.post(url, json={"resolution": "false_alarm", "note": " 확인해 보니 괜찮음 "})
    assert done.json()["resolution_note"] == "확인해 보니 괜찮음"
    assert client.post(url, json={"resolution": "acted"}).status_code == 409
    assert len(client.get("/org/alerts").json()) == 1
    resolved = client.get("/org/alerts", params={"status": "resolved"}).json()
    assert resolved[0]["resolved_by_name"] == "박담당"
    assert client.get("/org/alerts", params={"status": "all"}).status_code == 422


def test_concern_needs_health_consent(client: TestClient) -> None:
    signup(client)
    rid = add_recipient(client, consent=False)["id"]
    assert client.post(f"/recipients/{rid}/concerns", json={"note": "우려"}).status_code == 409
