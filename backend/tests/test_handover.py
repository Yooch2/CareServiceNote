import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.errors import PermanentAIError, TransientAIError
from app.ai.fake import FakeClassifier
from app.config import settings
from app.main import app
from app.models import FollowupCheck
from app.routers.handover import get_llm
from tests.helpers import add_recipient, make_confirmed, signup

TODAY = date.today()


@pytest.fixture
def llm() -> Iterator[FakeClassifier]:
    fake = FakeClassifier()
    app.dependency_overrides[get_llm] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm, None)


def _recipient(client: TestClient) -> uuid.UUID:
    signup(client)
    return uuid.UUID(add_recipient(client)["id"])


def _history(db: Session, rid: uuid.UUID) -> dict[str, object]:
    """20일 전(기간 밖), 5일 전, 2일 전 방문. 5일 전 '다음 확인' 하나는 2일 전에 확인됨"""
    old = make_confirmed(
        db,
        [("followup", "오래된 확인 사항"), ("remark", "허리가 아프다")],
        recipient_id=rid,
        visited_on=TODAY - timedelta(days=20),
        risk={1: "pain"},
    )
    mid = make_confirmed(
        db,
        [
            ("remark", "무릎이 불편하다"),
            ("followup", "무릎 상태 확인"),
            ("followup", "식사량 확인"),
        ],
        recipient_id=rid,
        visited_on=TODAY - timedelta(days=5),
        risk={0: "pain"},
    )
    recent = make_confirmed(
        db,
        [("observation", "점심을 반 정도 드심")],
        recipient_id=rid,
        visited_on=TODAY - timedelta(days=2),
    )
    db.add(
        FollowupCheck(
            followup_item_id=mid.items[1].id, record_id=recent.id, result="아직 불편", origin="ai"
        )
    )
    db.commit()
    return {"old": old, "mid": mid, "recent": recent}


def test_handover_bundle(client: TestClient, db: Session) -> None:
    rid = _recipient(client)
    h = _history(db, rid)
    make_confirmed(db, [("followup", "다른 수급자")])  # 섞이면 안 됨

    body = client.get(f"/recipients/{rid}/handover").json()
    assert body["days"] == 14
    assert body["last_visit_on"] == (TODAY - timedelta(days=2)).isoformat()
    # 남은 확인 사항은 기간과 관계없이 전부, 최근 방문 순
    assert [o["content"] for o in body["open_followups"]] == ["식사량 확인", "오래된 확인 사항"]
    # 위험 항목은 기간 안만
    assert [r["content"] for r in body["risk_items"]] == ["무릎이 불편하다"]
    assert [(c["followup_content"], c["result"]) for c in body["recent_checks"]] == [
        ("무릎 상태 확인", "아직 불편")
    ]
    assert body["recent_checks"][0]["record_id"] == str(h["recent"].id)  # type: ignore[attr-defined]
    assert body["completion"] == {"due": 2, "checked": 1}
    assert body["summary"] is None

    wide = client.get(f"/recipients/{rid}/handover?days=30").json()
    assert wide["completion"] == {"due": 3, "checked": 1}
    assert len(wide["risk_items"]) == 2
    assert client.get(f"/recipients/{rid}/handover?days=10").status_code == 422
    assert client.get(f"/recipients/{uuid.uuid4()}/handover").status_code == 404


def test_summary_is_saved_with_evidence_and_becomes_stale(
    client: TestClient, db: Session, llm: FakeClassifier
) -> None:
    rid = _recipient(client)
    h = _history(db, rid)

    res = client.post(f"/recipients/{rid}/handover/summary")
    assert res.status_code == 200, res.text
    summary = res.json()
    assert summary["stale"] is False
    # 가짜 모델은 첫 두 줄(가장 최근 방문 항목)을 옮긴다
    first = summary["sentences"][0]
    assert first["text"] == "점심을 반 정도 드심"
    assert first["items"] == [
        {
            "item_id": str(h["recent"].items[0].id),  # type: ignore[attr-defined]
            "record_id": str(h["recent"].id),  # type: ignore[attr-defined]
            "visited_on": (TODAY - timedelta(days=2)).isoformat(),
        }
    ]
    assert (
        client.get(f"/recipients/{rid}/handover").json()["summary"]["sentences"]
        == summary["sentences"]
    )
    # 요약 후 새 기록이 확정되면 stale
    make_confirmed(
        db,
        [("remark", "새 기록")],
        recipient_id=rid,
        visited_on=TODAY,
        confirmed_at=datetime.now(UTC) + timedelta(seconds=1),
    )
    assert client.get(f"/recipients/{rid}/handover").json()["summary"]["stale"] is True
    # 다른 기간의 요약은 따로
    assert client.get(f"/recipients/{rid}/handover?days=7").json()["summary"] is None


def test_summary_sends_no_names_or_ids(
    client: TestClient, db: Session, llm: FakeClassifier
) -> None:
    rid = _recipient(client)
    _history(db, rid)
    sent: list[str] = []
    original = llm.generate

    def spy(system: str, user: str, schema: type) -> object:  # noqa: ANN401
        sent.append(user)
        return original(system, user, schema)

    llm.generate = spy  # type: ignore[method-assign]
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 200
    assert "가상" not in sent[0] and str(rid) not in sent[0]
    assert "[확인 결과] 무릎 상태 확인 → 아직 불편" in sent[0]


def test_summary_errors(
    client: TestClient, db: Session, llm: FakeClassifier, monkeypatch: pytest.MonkeyPatch
) -> None:
    rid = _recipient(client)
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 422  # 기록 없음

    _history(db, rid)
    llm.failures.append(TransientAIError("gemini_http_429"))
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 503
    llm.failures.append(PermanentAIError("invalid_ai_output"))
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 502

    monkeypatch.setattr(settings, "daily_summaries_per_user", 1)
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 200
    assert client.post(f"/recipients/{rid}/handover/summary").status_code == 429
