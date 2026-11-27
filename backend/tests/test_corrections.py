"""6단계 PR①: 정정(사유·이력·권한), 정정 뒤 서명·요약·알림 처리, 감사 로그, 내보내기"""

import csv
import io
import uuid
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import evaluate_alerts
from app.models import Alert, AuditEvent, GuardianSummary, VisitRecord
from tests.helpers import colleague, make_confirmed, signup_center

D0 = date.today() - timedelta(days=3)


def _setup(client: TestClient, carer: TestClient, db: Session) -> tuple[str, dict]:
    """기관 담당자(client), 배정된 요양보호사(carer), 동의까지"""
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    for kind in ("health_record", "guardian_share"):
        client.post(f"/recipients/{rid}/consents", json={"kind": kind, "granted_on": "2026-11-01"})
    me = colleague(client, carer, assign_to=rid)
    return rid, me


def _visit(db: Session, rid: str, author: str, day: int, items, **kw) -> VisitRecord:  # noqa: ANN001
    record = make_confirmed(
        db,
        items,
        recipient_id=uuid.UUID(rid),
        caregiver_id=uuid.UUID(author),
        visited_on=D0 + timedelta(days=day),
        **kw,
    )
    evaluate_alerts(db, record)
    db.commit()
    return record


def _fix(client: TestClient, record: VisitRecord, i: int = 0, **change: object) -> Any:
    item = record.items[i]
    body = {
        "category": item.category,
        "content": item.content,
        "body_part": item.body_part,
        "risk_tag": item.risk_tag,
        "reason": "녹음을 다시 들어 보니 달랐음",
        **change,
    }
    return client.patch(f"/records/{record.id}/items/{item.id}", json=body)


def test_correction_rules_and_history(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    record = _visit(db, rid, carer["id"], 0, [("remark", "무릎이 불편하다")], parts={0: "knee"})

    assert _fix(other_client, record, reason="  ").status_code == 422  # 사유 필수
    assert _fix(other_client, record).status_code == 422  # 바뀐 것 없음
    res = _fix(other_client, record, content="허리가 불편하다", body_part="back")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["items"][0]["content"] == "허리가 불편하다"
    [rev] = body["revisions"]
    assert rev["before"]["content"] == "무릎이 불편하다" and rev["after"]["body_part"] == "back"
    assert rev["user_name"] == "동료" and rev["reason"] == "녹음을 다시 들어 보니 달랐음"

    # 기관 담당자도 정정할 수 있고, 오늘 상태도 정정된다
    state = client.patch(
        f"/records/{record.id}/state", json={"meal_level": 1, "mood": "low", "reason": "다시 확인"}
    ).json()
    assert (state["meal_level"], state["mood"]) == (1, "low") and len(state["revisions"]) == 2


def test_other_caregiver_and_unconfirmed_cannot_be_corrected(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    third = TestClient(other_client.app)
    colleague(client, third, "carer77", assign_to=rid)
    record = _visit(db, rid, carer["id"], 0, [("remark", "산책을 원하심")])
    assert _fix(third, record, content="바꿈").status_code == 403

    record.status, record.confirmed_at = "draft_ready", None
    db.commit()
    assert _fix(other_client, record, content="바꿈").status_code == 409


def test_correction_resets_review_and_unapproves_summary(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    record = _visit(
        db, rid, carer["id"], 0, [("remark", "손녀 이야기"), ("observation", "잘 드심")]
    )
    client.post(f"/records/{record.id}/review")
    client.post(f"/records/{record.id}/guardian-summary")
    client.post(f"/records/{record.id}/guardian-summary/approve")

    _fix(other_client, record, 1, content="반만 드심")  # 관찰 항목 정정
    after = client.get(f"/records/{record.id}").json()
    assert after["review"] is None  # 다시 확인 대기
    db.expire_all()
    summary = db.scalar(select(GuardianSummary).where(GuardianSummary.record_id == record.id))
    assert summary is not None and summary.status == "draft"


def test_correction_reevaluates_alerts(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    knee = [("remark", "무릎이 불편하다")]
    first = _visit(db, rid, carer["id"], 0, knee, parts={0: "knee"})
    _visit(db, rid, carer["id"], 2, knee, parts={0: "knee"})
    [alert] = client.get(f"/recipients/{rid}/alerts").json()
    assert alert["key"] == "knee"

    # 첫 방문이 사실 허리였다 → 무릎 반복 조건이 사라져 닫힘
    _fix(other_client, first, content="허리가 불편하다", body_part="back")
    assert client.get(f"/recipients/{rid}/alerts").json() == []
    db.expire_all()
    closed = db.get(Alert, uuid.UUID(alert["id"]))
    assert closed is not None and closed.resolution == "corrected"

    # 다른 방문도 허리라면 허리 반복 알림이 새로 생긴다
    third = _visit(db, rid, carer["id"], 3, knee, parts={0: "knee"})
    _fix(other_client, third, content="허리가 아프다", body_part="back")
    assert [a["key"] for a in client.get(f"/recipients/{rid}/alerts").json()] == ["back"]


def test_meal_correction_reevaluates(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    _visit(db, rid, carer["id"], 0, [("remark", "a")], meal_level=4)
    second = _visit(db, rid, carer["id"], 1, [("remark", "b")], meal_level=1)
    assert [a["kind"] for a in client.get(f"/recipients/{rid}/alerts").json()] == ["meal_drop"]
    client.patch(f"/records/{second.id}/state", json={"meal_level": 3, "reason": "다시 확인"})
    assert client.get(f"/recipients/{rid}/alerts").json() == []


def test_audit_log_records_actions_without_content(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    record = _visit(db, rid, carer["id"], 0, [("remark", "무릎이 불편하다")])
    other_client.get(f"/records/{record.id}")
    other_client.get(f"/recipients/{rid}/handover")
    other_client.get(f"/recipients/{rid}/search", params={"q": "무릎"})
    _fix(other_client, record, content="무릎이 쑤신다")
    client.get(f"/recipients/{rid}/export")

    log = client.get(f"/recipients/{rid}/audit").json()
    assert [e["action"] for e in reversed(log)] == [
        "view_record",
        "view_handover",
        "search",
        "correct",
        "export",
    ]
    assert {e["actor_name"] for e in log} == {"동료", "박담당"}
    stored = db.scalars(select(AuditEvent)).all()
    assert "무릎" not in str([vars(e) for e in stored])  # 검색어·내용은 남지 않음


def test_export_csv(client: TestClient, other_client: TestClient, db: Session) -> None:
    rid, carer = _setup(client, other_client, db)
    record = _visit(
        db, rid, carer["id"], 0, [("remark", "무릎이 불편하다"), ("followup", "무릎 다시 확인")]
    )
    record.meal_level = 2
    db.commit()
    _fix(other_client, record, content="무릎이 쑤신다")

    res = client.get(f"/recipients/{rid}/export")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    disposition = res.headers["content-disposition"]
    assert f"records-{rid}.csv" in disposition and "가상수급자" not in disposition
    assert res.content.startswith("﻿".encode())
    rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert rows[0][:3] == ["방문일", "분류", "내용"]
    assert [(r[1], r[2], r[5], r[7]) for r in rows[1:]] == [
        ("말씀", "무릎이 쑤신다", "예", "절반"),
        ("다음 확인", "무릎 다시 확인", "", "절반"),
    ]


def test_export_neutralizes_formulas(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    _visit(
        db,
        rid,
        carer["id"],
        0,
        [("remark", '=HYPERLINK("http://x","클릭")'), ("remark", "-3kg 빠지심")],
    )
    rows = list(
        csv.reader(io.StringIO(client.get(f"/recipients/{rid}/export").content.decode("utf-8-sig")))
    )
    assert [r[2] for r in rows[1:]] == ['\'=HYPERLINK("http://x","클릭")', "'-3kg 빠지심"]


def test_correction_needs_health_consent(
    client: TestClient, other_client: TestClient, db: Session
) -> None:
    rid, carer = _setup(client, other_client, db)
    record = _visit(db, rid, carer["id"], 0, [("remark", "산책을 원하심")])
    consent = next(
        c
        for c in client.get(f"/recipients/{rid}/admin").json()["consents"]
        if c["kind"] == "health_record"
    )
    client.post(f"/recipients/{rid}/consents/{consent['id']}/withdraw")
    assert _fix(other_client, record, content="바꿈").status_code == 409
