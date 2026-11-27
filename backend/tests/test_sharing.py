"""5단계: 보호자 하루 요약(승인·열람 범위), 방문 시작/종료, 처리 결과 공유, 업무 메시지"""

import uuid
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from tests.helpers import PASSWORD, colleague, make_confirmed, signup_center

ITEMS = [
    ("remark", "손녀 이야기를 하심"),
    ("observation", "식사를 절반 남기심"),
    ("followup", "식사량 다시 확인"),
]


def _guardian(client: TestClient, rid: str, login_id: str, categories: list[str]) -> TestClient:
    code = client.post(
        "/org/invites", json={"role": "guardian", "recipient_id": rid, "categories": categories}
    ).json()["code"]
    g = TestClient(app)
    res = g.post(
        "/auth/signup",
        json={
            "login_id": login_id,
            "password": PASSWORD,
            "display_name": "가족",
            "invite_code": code,
        },
    )
    assert res.status_code == 201
    return g


def _world(client: TestClient, db: Session, share: bool = True) -> tuple[str, str]:
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    kinds = ["health_record", "guardian_share"] if share else ["health_record"]
    for kind in kinds:
        client.post(f"/recipients/{rid}/consents", json={"kind": kind, "granted_on": "2026-11-01"})
    record = make_confirmed(db, ITEMS, recipient_id=uuid.UUID(rid), visited_on=date.today())
    return rid, str(record.id)


def _summaries(g: TestClient) -> list[str]:
    return [s for r in g.get("/guardian/home").json()["records"] for s in r["summary"]]


def test_summary_needs_approval_and_is_filtered_per_guardian(
    client: TestClient, db: Session
) -> None:
    rid, record_id = _world(client, db)
    narrow = _guardian(client, rid, "family01", ["remark"])
    wide = _guardian(client, rid, "family02", ["remark", "observation", "followup"])

    made = client.post(f"/records/{record_id}/guardian-summary")
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["status"] == "draft"
    assert [s["categories"] for s in body["sentences"]] == [
        ["remark"],
        ["observation"],
        ["followup"],
    ]
    assert _summaries(narrow) == []  # 승인 전에는 안 보임

    client.post(f"/records/{record_id}/guardian-summary/approve")
    assert _summaries(narrow) == ["손녀 이야기를 하심"]
    assert _summaries(wide) == [t for _, t in ITEMS]

    # 승인된 요약은 다시 만들거나 고칠 수 없다
    assert client.post(f"/records/{record_id}/guardian-summary").status_code == 409
    edit = {"sentences": [{"text": "x"}] * 3}
    assert client.put(f"/records/{record_id}/guardian-summary", json=edit).status_code == 409
    client.post(f"/records/{record_id}/guardian-summary/unapprove")
    assert _summaries(wide) == []


def test_edit_keeps_evidence_and_cannot_add(client: TestClient, db: Session) -> None:
    rid, record_id = _world(client, db)
    narrow = _guardian(client, rid, "family01", ["remark"])
    client.post(f"/records/{record_id}/guardian-summary")
    url = f"/records/{record_id}/guardian-summary"

    too_many = {"sentences": [{"text": "a"}] * 4}
    assert client.put(url, json=too_many).status_code == 422
    edited = client.put(
        url,
        json={
            "sentences": [
                {"text": "어르신이 손녀 이야기를 즐겁게 하셨어요"},
                {"text": ""},
                {"text": "식사량 다시 확인"},
            ]
        },
    ).json()
    assert [s["text"] for s in edited["sentences"]] == [
        "어르신이 손녀 이야기를 즐겁게 하셨어요",
        "식사량 다시 확인",
    ]
    assert [s["edited"] for s in edited["sentences"]] == [True, False]
    assert edited["sentences"][0]["categories"] == ["remark"]  # 근거는 그대로

    client.post(f"{url}/approve")
    assert _summaries(narrow) == ["어르신이 손녀 이야기를 즐겁게 하셨어요"]


def test_summary_input_has_no_transcript_and_needs_share_consent(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    rid, record_id = _world(client, db, share=False)
    assert client.post(f"/records/{record_id}/guardian-summary").status_code == 409

    client.post(
        f"/recipients/{rid}/consents", json={"kind": "guardian_share", "granted_on": "2026-11-01"}
    )
    seen: dict[str, Any] = {}
    from app.ai import fake

    original = fake.FakeClassifier.generate

    def spy(self: Any, system: str, user: str, schema: Any) -> Any:
        seen["user"] = user
        return original(self, system, user, schema)

    monkeypatch.setattr(fake.FakeClassifier, "generate", spy)
    assert client.post(f"/records/{record_id}/guardian-summary").status_code == 200
    assert seen["user"].splitlines()[1:] == [
        "I1. [말씀] 손녀 이야기를 하심",
        "I2. [관찰] 식사를 절반 남기심",
        "I3. [다음 확인] 식사량 다시 확인",
    ]
    assert "가상수급자" not in seen["user"] and record_id not in seen["user"]


def test_summary_shares_daily_ai_limit(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    rid, record_id = _world(client, db)
    monkeypatch.setattr(settings, "daily_summaries_per_user", 1)
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 200
    assert client.post(f"/records/{record_id}/guardian-summary").status_code == 429


def test_visit_start_end(client: TestClient, other_client: TestClient, db: Session) -> None:
    rid, _ = _world(client, db)
    rid2 = client.post("/recipients", json={"name": "가상수급자2"}).json()["id"]
    carer = colleague(client, other_client, assign_to=rid)
    client.post(f"/recipients/{rid2}/assignments", json={"caregiver_id": carer["id"]})
    family = _guardian(client, rid, "family01", ["remark"])

    assert other_client.post(f"/recipients/{rid}/visits/end").status_code == 409
    started = other_client.post(f"/recipients/{rid}/visits/start")
    assert started.status_code == 201
    # 끝내지 않고 다른 수급자 방문을 시작할 수 없다
    assert other_client.post(f"/recipients/{rid2}/visits/start").status_code == 409
    assert other_client.post(f"/recipients/{rid2}/visits/end").status_code == 409

    [session] = family.get("/guardian/home").json()["sessions"]
    assert session["ended_at"] is None and "caregiver" not in str(session)
    ended = other_client.post(f"/recipients/{rid}/visits/end").json()
    assert ended["ended_at"] is not None
    assert [v["caregiver_name"] for v in client.get(f"/recipients/{rid}/visits").json()] == ["동료"]
    assert other_client.post(f"/recipients/{rid2}/visits/start").status_code == 201


def test_resolved_alert_shares_only_guardian_message(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, _ = _world(client, db)
    colleague(client, other_client, assign_to=rid)
    family = _guardian(client, rid, "family01", ["remark", "observation"])
    narrow = _guardian(client, rid, "family02", ["remark"])
    other_client.post(f"/recipients/{rid}/concerns", json={"note": "숨이 차 보이심 (내부 메모)"})
    other_client.post(f"/recipients/{rid}/concerns", json={"note": "두 번째 우려"})
    first, second = client.get("/org/alerts").json()
    # 인박스에 보호자별 열람 범위가 같이 온다
    assert sorted(sorted(g["categories"]) for g in first["guardians"]) == [
        ["observation", "remark"],
        ["remark"],
    ]
    targets = [g["guardian_id"] for g in first["guardians"] if "observation" in g["categories"]]

    url = f"/org/alerts/{first['id']}/resolve"
    message = {"resolution": "acted", "guardian_message": " 병원 진료를 예약했습니다. "}
    # 안내문이 있으면 받을 보호자를 골라야 하고, 이 수급자의 보호자만 고를 수 있다
    assert client.post(url, json=message).status_code == 422
    stranger = {**message, "guardian_ids": [str(uuid.uuid4())]}
    assert client.post(url, json=stranger).status_code == 422
    done = client.post(url, json={**message, "note": "내부 처리 메모", "guardian_ids": targets})
    assert done.status_code == 200
    client.post(f"/org/alerts/{second['id']}/resolve", json={"resolution": "false_alarm"})

    res = family.get("/guardian/home")
    assert [n["message"] for n in res.json()["notices"]] == ["병원 진료를 예약했습니다."]
    for secret in ("숨이 차", "내부 처리 메모", "두 번째 우려"):
        assert secret not in res.text
    assert narrow.get("/guardian/home").json()["notices"] == []  # 고르지 않은 보호자는 못 봄


def test_messages(client: TestClient, other_client: TestClient, db: Session) -> None:
    rid, _ = _world(client, db)
    colleague(client, other_client, assign_to=rid)
    client.post(f"/recipients/{rid}/messages", json={"body": "내일 방문은 10시로 바뀌었습니다"})
    other_client.post(f"/recipients/{rid}/messages", json={"body": "확인했습니다"})
    assert other_client.post(f"/recipients/{rid}/messages", json={"body": "  "}).status_code == 422
    listed = other_client.get(f"/recipients/{rid}/messages").json()
    assert [(m["author_role"], m["body"]) for m in listed] == [
        ("manager", "내일 방문은 10시로 바뀌었습니다"),
        ("caregiver", "확인했습니다"),
    ]
