import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import worker
from app.ai.fake import FakeClassifier, FakeTranscriber
from app.ai.types import Classifier, Transcriber
from app.config import settings
from app.db import SessionLocal
from app.models import Recipient, RecordItem, User, VisitRecord


def signup(
    client: TestClient,
    login_id: str = "carer01",
    password: str = "password123",
    display_name: str = "김요양",
) -> dict[str, Any]:
    res = client.post(
        "/auth/signup",
        json={"login_id": login_id, "password": password, "display_name": display_name},
    )
    assert res.status_code == 201, res.text
    return res.json()


def add_recipient(client: TestClient, name: str = "가상수급자") -> dict[str, Any]:
    res = client.post("/recipients", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def put_audio(
    client: TestClient,
    record_id: str,
    recipient_id: str,
    *,
    content: bytes = b"fake-audio",
    content_type: str = "audio/webm",
):  # 반환 타입: TestClient 응답 (httpx 또는 httpx2, 설치된 쪽을 따라감)
    return client.put(
        f"/records/{record_id}",
        data={
            "recipient_id": recipient_id,
            "visited_on": "2026-11-27",
            "recorded_at": "2026-11-27T10:00:00+09:00",
        },
        files={"audio": ("rec", content, content_type)},
    )


def set_draft(
    db: Session, record_id: str, draft: dict[str, Any] | None, status: str = "draft_ready"
) -> None:
    record = db.get(VisitRecord, uuid.UUID(record_id))
    assert record is not None
    record.draft = draft
    record.status = status
    db.commit()


def make_record(
    db: Session,
    *,
    status: str = "queued",
    transcript: str | None = None,
    with_audio: bool = True,
    recipient_id: uuid.UUID | None = None,
) -> VisitRecord:
    user = User(login_id=f"w{uuid.uuid4().hex[:8]}", password_hash="x", display_name="워커테스트")
    db.add(user)
    if recipient_id is None:
        recipient = Recipient(name="가상수급자")
        db.add(recipient)
        db.flush()
        recipient_id = recipient.id
    db.flush()
    record_id = uuid.uuid4()
    audio_path = None
    if with_audio:
        settings.audio_dir.mkdir(parents=True, exist_ok=True)
        path = settings.audio_dir / f"{record_id}.webm"
        path.write_bytes(b"fake-audio")
        audio_path = str(path)
    record = VisitRecord(
        id=record_id,
        recipient_id=recipient_id,
        caregiver_id=user.id,
        visited_on=date(2026, 11, 27),
        recorded_at=datetime(2026, 11, 27, 1, 0, tzinfo=UTC),
        status=status,
        transcript=transcript,
        audio_path=audio_path,
    )
    db.add(record)
    db.commit()
    return record


def process_all(
    transcriber: Transcriber | None = None, classifier: Classifier | None = None
) -> None:
    """백오프를 무시하고 남은 작업을 모두 처리한다 (API 통합 테스트용)."""
    far_future = datetime.now(UTC) + timedelta(days=1)
    t = transcriber or FakeTranscriber()
    c = classifier or FakeClassifier()
    while worker.run_once(SessionLocal, t, c, lambda: far_future):
        pass


def make_confirmed(
    db: Session,
    items: list[tuple[str, str]],
    *,
    recipient_id: uuid.UUID | None = None,
    caregiver_id: uuid.UUID | None = None,
    visited_on: date = date(2026, 11, 20),
    transcript: str | None = None,
    confirmed_at: datetime | None = None,
    risk: dict[int, str] | None = None,
) -> VisitRecord:
    """확정된 방문 기록을 바로 만든다. items는 (분류, 내용) 목록, risk는 {순번: 위험 태그}."""
    if recipient_id is None:
        recipient = Recipient(name="가상수급자")
        db.add(recipient)
        db.flush()
        recipient_id = recipient.id
    if caregiver_id is None:
        user = User(
            login_id=f"c{uuid.uuid4().hex[:8]}", password_hash="x", display_name="확정테스트"
        )
        db.add(user)
        db.flush()
        caregiver_id = user.id
    record = VisitRecord(
        id=uuid.uuid4(),
        recipient_id=recipient_id,
        caregiver_id=caregiver_id,
        visited_on=visited_on,
        recorded_at=datetime.combine(visited_on, datetime.min.time(), UTC),
        status="confirmed",
        transcript=transcript,
        confirmed_at=confirmed_at or datetime.now(UTC),
        items=[
            RecordItem(
                category=category,
                content=content,
                evidence=content,
                origin="ai",
                position=i,
                risk_tag=(risk or {}).get(i),
            )
            for i, (category, content) in enumerate(items)
        ],
    )
    db.add(record)
    db.commit()
    return record
