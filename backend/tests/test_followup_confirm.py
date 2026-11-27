import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.confirm import build_followup_checks
from app.schemas import ConfirmIn
from tests.helpers import add_recipient, make_confirmed, put_audio, set_draft, signup


def _setup(client: TestClient, db: Session) -> tuple[str, list[str], str]:
    """가입 → 수급자 → 이전 확정 기록(다음 확인 2개) → 새 녹음 업로드"""
    signup(client)
    rid = add_recipient(client)["id"]
    earlier = make_confirmed(
        db,
        [("followup", "무릎 상태 다시 확인"), ("followup", "산책 의향 확인")],
        recipient_id=uuid.UUID(rid),
    )
    record_id = str(uuid.uuid4())
    assert put_audio(client, record_id, rid).status_code == 201
    return rid, [str(i.id) for i in earlier.items], record_id


def _draft(followup_ids: list[str], suggested: list[str]) -> dict[str, Any]:
    return {
        "items": [],
        "missing_topics": [],
        "open_followups": [
            {"item_id": i, "content": "내용", "visited_on": "2026-11-20"} for i in followup_ids
        ],
        "followup_results": [
            {
                "item_id": i,
                "result": "아직 불편하다고 하심",
                "evidence": "무릎이 불편",
                "evidence_found": True,
                "segment_index": 0,
            }
            for i in suggested
        ],
    }


def test_build_followup_checks_origin_and_coverage() -> None:
    a, b, c = (str(uuid.uuid4()) for _ in range(3))
    draft = _draft([a, b, c], [a, b])
    body = ConfirmIn.model_validate(
        {
            "followup_checks": [
                {"item_id": a, "result": "아직 불편하다고 하심"},
                {"item_id": c, "result": "산책은 다음 주에"},
            ],
            "dismissed_followup_items": [b],
        }
    )
    checks = build_followup_checks(draft, body)
    assert [(str(x["followup_item_id"]), x["origin"]) for x in checks] == [(a, "ai"), (c, "human")]

    edited = ConfirmIn.model_validate(
        {
            "followup_checks": [{"item_id": a, "result": "조금 나아졌다고 하심"}],
            "dismissed_followup_items": [b],
        }
    )
    assert build_followup_checks(draft, edited)[0]["origin"] == "ai_edited"


def test_confirm_links_results_to_original_items(client: TestClient, db: Session) -> None:
    _, (knee, walk), record_id = _setup(client, db)
    set_draft(db, record_id, _draft([knee, walk], [knee]))

    res = client.post(
        f"/records/{record_id}/confirm",
        json={
            "followup_checks": [
                {"item_id": knee, "result": "아직 불편하다고 하심", "evidence": "무릎이 불편"},
                {"item_id": walk, "result": "오늘은 집에서 쉬고 싶다고 하심"},
            ]
        },
    )
    assert res.status_code == 200, res.text
    checks = res.json()["followup_checks"]
    assert [(c["followup_item_id"], c["origin"]) for c in checks] == [(knee, "ai"), (walk, "human")]
    assert checks[0]["followup_content"] == "무릎 상태 다시 확인"
    assert checks[0]["followup_visited_on"] == "2026-11-20"

    earlier_id = checks[0]["followup_record_id"]
    earlier = client.get(f"/records/{earlier_id}").json()
    knee_item = next(i for i in earlier["items"] if i["id"] == knee)
    assert knee_item["check"]["result"] == "아직 불편하다고 하심"
    assert knee_item["check"]["record_id"] == record_id


def test_unhandled_suggestion_is_rejected(client: TestClient, db: Session) -> None:
    _, (knee, walk), record_id = _setup(client, db)
    set_draft(db, record_id, _draft([knee, walk], [knee]))
    res = client.post(
        f"/records/{record_id}/confirm",
        json={"items": [{"category": "remark", "content": "괜찮다고 하심"}]},
    )
    assert res.status_code == 422
    assert "모두 확인하거나 삭제" in res.json()["detail"]

    dismissed = client.post(
        f"/records/{record_id}/confirm",
        json={
            "items": [{"category": "remark", "content": "괜찮다고 하심"}],
            "dismissed_followup_items": [knee],
        },
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["followup_checks"] == []


def test_cannot_check_other_recipients_item_or_twice(client: TestClient, db: Session) -> None:
    rid, (knee, _), record_id = _setup(client, db)
    other = make_confirmed(db, [("followup", "다른 수급자 확인 사항")])
    remark = make_confirmed(db, [("remark", "말씀")], recipient_id=uuid.UUID(rid))
    set_draft(db, record_id, None, status="failed")

    for item_id in (str(other.items[0].id), str(remark.items[0].id), str(uuid.uuid4())):
        res = client.post(
            f"/records/{record_id}/confirm",
            json={"followup_checks": [{"item_id": item_id, "result": "확인"}]},
        )
        assert res.status_code == 422, item_id

    ok = client.post(
        f"/records/{record_id}/confirm",
        json={"followup_checks": [{"item_id": knee, "result": "직접 확인함"}]},
    )
    assert ok.status_code == 200
    assert ok.json()["followup_checks"][0]["origin"] == "human"

    second_id = str(uuid.uuid4())
    assert put_audio(client, second_id, rid).status_code == 201
    set_draft(db, second_id, None, status="failed")
    again = client.post(
        f"/records/{second_id}/confirm",
        json={"followup_checks": [{"item_id": knee, "result": "또 확인"}]},
    )
    assert again.status_code == 409


def test_confirm_needs_items_or_checks(client: TestClient, db: Session) -> None:
    _, _, record_id = _setup(client, db)
    set_draft(db, record_id, None, status="failed")
    assert client.post(f"/records/{record_id}/confirm", json={}).status_code == 422
