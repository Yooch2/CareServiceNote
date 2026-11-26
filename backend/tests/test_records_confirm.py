import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models import VisitRecord
from tests.helpers import add_recipient, put_audio, set_draft, signup

DRAFT = {
    "items": [
        {
            "category": "remark",
            "content": "무릎이 아프다",
            "evidence": "무릎이 아프다고",
            "evidence_found": True,
            "segment_index": 0,
            "speaker_uncertain": False,
            "risk_tag": "pain",
        }
    ],
    "missing_topics": ["meal"],
}


def _uploaded(client: TestClient) -> str:
    signup(client)
    rid = add_recipient(client)["id"]
    record_id = str(uuid.uuid4())
    assert put_audio(client, record_id, rid).status_code == 201
    return record_id


def test_confirm_creates_items_and_deletes_audio(client: TestClient, db: Session) -> None:
    record_id = _uploaded(client)
    set_draft(db, record_id, DRAFT)
    record = db.get(VisitRecord, uuid.UUID(record_id))
    assert record is not None and record.audio_path is not None
    audio_path = record.audio_path
    assert Path(audio_path).exists()

    res = client.post(
        f"/records/{record_id}/confirm",
        json={
            "items": [
                {
                    "draft_index": 0,
                    "category": "remark",
                    "content": "무릎이 아프다",
                    "evidence": "무릎이 아프다고",
                    "risk_tag": "pain",
                },
                {"category": "followup", "content": "다음에 무릎 상태 확인"},
            ]
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "confirmed"
    assert body["confirmed_at"] is not None
    assert body["has_audio"] is False
    assert [(i["origin"], i["position"]) for i in body["items"]] == [("ai", 0), ("human", 1)]
    assert body["draft"] == DRAFT
    assert not Path(audio_path).exists()

    again = client.post(
        f"/records/{record_id}/confirm",
        json={"items": [{"category": "remark", "content": "x"}]},
    )
    assert again.status_code == 409


def test_confirm_rejects_unreviewed_draft(client: TestClient, db: Session) -> None:
    record_id = _uploaded(client)
    set_draft(db, record_id, DRAFT)
    res = client.post(
        f"/records/{record_id}/confirm", json={"items": [{"category": "remark", "content": "x"}]}
    )
    assert res.status_code == 422


def test_confirm_failed_record_with_manual_items(client: TestClient, db: Session) -> None:
    record_id = _uploaded(client)
    set_draft(db, record_id, None, status="failed")
    res = client.post(
        f"/records/{record_id}/confirm",
        json={"items": [{"category": "observation", "content": "직접 작성한 관찰"}]},
    )
    assert res.status_code == 200
    assert res.json()["items"][0]["origin"] == "human"


def test_confirm_blocked_while_processing_or_by_others(client: TestClient, db: Session) -> None:
    record_id = _uploaded(client)
    body = {"items": [{"category": "remark", "content": "x"}]}
    assert client.post(f"/records/{record_id}/confirm", json=body).status_code == 409

    set_draft(db, record_id, DRAFT)
    with TestClient(app) as other:
        signup(other, login_id="carer99")
        assert other.post(f"/records/{record_id}/confirm", json=body).status_code == 404
