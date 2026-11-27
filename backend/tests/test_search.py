import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import FollowupCheck
from app.routers.search import like_pattern, snippet
from tests.helpers import add_recipient, make_confirmed, make_record, signup

TODAY = date.today()


def test_like_pattern_escapes_wildcards() -> None:
    assert like_pattern("50%_\\") == "%50\\%\\_\\\\%"


def test_snippet_cuts_around_match() -> None:
    text = "가" * 100 + "무릎" + "나" * 100
    cut = snippet(text, "무릎", width=5)
    assert cut == "…가가가가가무릎나나나나나…"
    assert snippet("짧은 무릎 문장", "무릎") == "짧은 무릎 문장"


def _setup(client: TestClient, db: Session) -> uuid.UUID:
    signup(client)
    rid = uuid.UUID(add_recipient(client)["id"])
    first = make_confirmed(
        db,
        [("remark", "오른쪽 무릎이 불편하다"), ("followup", "무릎 상태 다시 확인")],
        recipient_id=rid,
        visited_on=TODAY - timedelta(days=20),
        transcript="오늘 어르신이 오른쪽 무릎이 좀 불편하다고 하셨어요.",
    )
    second = make_confirmed(
        db,
        [("observation", "점심을 100% 드심")],
        recipient_id=rid,
        visited_on=TODAY - timedelta(days=2),
        transcript="점심은 다 드셨고 산책은 다음 주에 하고 싶다고 하셨어요.",
    )
    db.add(
        FollowupCheck(
            followup_item_id=first.items[1].id,
            record_id=second.id,
            result="무릎은 조금 나아졌다고 하심",
            origin="ai",
        )
    )
    db.commit()
    return rid


def test_search_items_checks_and_transcripts(client: TestClient, db: Session) -> None:
    rid = _setup(client, db)
    make_confirmed(db, [("remark", "다른 수급자 무릎")])  # 다른 수급자
    pending = make_record(db, recipient_id=rid, transcript="확정 전 무릎 전사문")
    assert pending.status == "queued"

    hits = client.get(f"/recipients/{rid}/search", params={"q": " 무릎 "}).json()
    kinds = sorted((h["kind"], h["visited_on"]) for h in hits)
    recent, old = (TODAY - timedelta(days=2)).isoformat(), (TODAY - timedelta(days=20)).isoformat()
    assert kinds == [
        ("check", recent),
        ("item", old),
        ("item", old),
        ("transcript", old),
    ]
    assert hits[0]["visited_on"] == recent  # 최근 방문부터
    assert all("다른 수급자" not in h["text"] and "확정 전" not in h["text"] for h in hits)
    check = next(h for h in hits if h["kind"] == "check")
    assert check["text"] == "무릎 상태 다시 확인 → 무릎은 조금 나아졌다고 하심"


def test_search_filters_and_validation(client: TestClient, db: Session) -> None:
    rid = _setup(client, db)
    url = f"/recipients/{rid}/search"
    only_remarks = client.get(url, params={"q": "무릎", "category": "remark"}).json()
    assert [(h["kind"], h["category"]) for h in only_remarks] == [("item", "remark")]

    recent = client.get(url, params={"q": "무릎", "days": 7}).json()
    assert [h["kind"] for h in recent] == ["check"]

    assert [h["text"] for h in client.get(url, params={"q": "100%"}).json()] == ["점심을 100% 드심"]
    assert client.get(url, params={"q": "0%"}).json() != []
    assert client.get(url, params={"q": "%"}).status_code == 422
    assert client.get(url, params={"q": "가" * 51}).status_code == 422
    assert client.get(url, params={"q": "없는말없는말"}).json() == []
