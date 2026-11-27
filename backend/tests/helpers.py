import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import worker
from app.ai.fake import FakeClassifier, FakeTranscriber
from app.ai.types import Classifier, Transcriber
from app.config import settings
from app.db import SessionLocal
from app.invites import hash_code
from app.models import (
    Assignment,
    Consent,
    Invite,
    Organization,
    Recipient,
    RecordItem,
    User,
    VisitRecord,
)

PASSWORD = "password123"


def new_org(db: Session, name: str = "가상센터") -> Organization:
    org = Organization(name=name)
    db.add(org)
    db.flush()
    return org


def make_user(db: Session, org_id: uuid.UUID, role: str = "caregiver", **kw: Any) -> User:
    user = User(
        org_id=org_id,
        role=role,
        login_id=kw.pop("login_id", f"u{uuid.uuid4().hex[:8]}"),
        password_hash=kw.pop("password_hash", "x"),
        display_name=kw.pop("display_name", "테스트"),
        **kw,
    )
    db.add(user)
    db.flush()
    return user


def make_invite(
    db: Session,
    org_id: uuid.UUID,
    created_by: uuid.UUID,
    code: str,
    role: str = "caregiver",
    **kw: Any,
) -> Invite:
    invite = Invite(
        org_id=org_id,
        role=role,
        code_hash=hash_code(code),
        expires_at=kw.pop("expires_at", datetime.now(UTC) + timedelta(days=7)),
        created_by=created_by,
        **kw,
    )
    db.add(invite)
    db.commit()
    return invite


def signup_center(
    client: TestClient, login_id: str = "boss01", center_name: str = "가상센터"
) -> dict[str, Any]:
    """센터를 새로 만들고 기관 담당자로 로그인한다."""
    res = client.post(
        "/auth/signup",
        json={
            "login_id": login_id,
            "password": PASSWORD,
            "display_name": "박담당",
            "center_name": center_name,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def signup(
    client: TestClient,
    login_id: str = "carer01",
    password: str = PASSWORD,
    display_name: str = "김요양",
) -> dict[str, Any]:
    """새 센터의 초대 코드로 요양보호사 가입·로그인한다 (기관 담당자는 DB에 직접 만든다)."""
    with SessionLocal() as db:
        org = new_org(db)
        manager = make_user(db, org.id, "manager")
        code = f"T{uuid.uuid4().hex[:9].upper()}"
        make_invite(db, org.id, manager.id, code)
    res = client.post(
        "/auth/signup",
        json={
            "login_id": login_id,
            "password": password,
            "display_name": display_name,
            "invite_code": code,
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


def add_recipient(
    client: TestClient, name: str = "가상수급자", *, consent: bool = True
) -> dict[str, Any]:
    """로그인한 요양보호사의 센터에 수급자를 만들고 배정한다 (건강정보 동의 포함)."""
    me = client.get("/auth/me").json()
    with SessionLocal() as db:
        user = db.get(User, uuid.UUID(me["id"]))
        assert user is not None
        recipient = Recipient(name=name, org_id=user.org_id)
        db.add(recipient)
        db.flush()
        assign(db, recipient.id, user.id)
        if consent:
            give_consent(db, recipient.id, user.id)
        db.commit()
        recipient_id = recipient.id
    res = client.get(f"/recipients/{recipient_id}")
    assert res.status_code == 200, res.text
    return res.json()


def assign(db: Session, recipient_id: uuid.UUID, caregiver_id: uuid.UUID) -> Assignment:
    a = Assignment(recipient_id=recipient_id, caregiver_id=caregiver_id, created_by=caregiver_id)
    db.add(a)
    db.flush()
    return a


def give_consent(
    db: Session, recipient_id: uuid.UUID, by: uuid.UUID, kind: str = "health_record"
) -> Consent:
    c = Consent(recipient_id=recipient_id, kind=kind, granted_on=date(2026, 11, 1), recorded_by=by)
    db.add(c)
    db.flush()
    return c


def login(client: TestClient, login_id: str, password: str = PASSWORD) -> None:
    res = client.post("/auth/login", json={"login_id": login_id, "password": password})
    assert res.status_code == 200, res.text


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
    org = new_org(db)
    user = make_user(db, org.id, display_name="워커테스트")
    if recipient_id is None:
        recipient = Recipient(name="가상수급자", org_id=org.id)
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
        recipient = Recipient(name="가상수급자", org_id=new_org(db).id)
        db.add(recipient)
        db.flush()
        recipient_id = recipient.id
    if caregiver_id is None:
        org_id = db.scalar(select(Recipient.org_id).where(Recipient.id == recipient_id))
        assert org_id is not None
        caregiver_id = make_user(db, org_id, display_name="확정테스트").id
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


def colleague(
    member: TestClient,
    other: TestClient,
    login_id: str = "carer99",
    *,
    role: str = "caregiver",
    assign_to: str | None = None,
) -> dict[str, Any]:
    """member와 같은 센터에 초대 코드로 가입시킨다. assign_to(수급자 id)를 주면 배정까지."""
    me = member.get("/auth/me").json()
    with SessionLocal() as db:
        user = db.get(User, uuid.UUID(me["id"]))
        assert user is not None
        code = f"T{uuid.uuid4().hex[:9].upper()}"
        make_invite(db, user.org_id, user.id, code, role)
    res = other.post(
        "/auth/signup",
        json={
            "login_id": login_id,
            "password": PASSWORD,
            "display_name": "동료",
            "invite_code": code,
        },
    )
    assert res.status_code == 201, res.text
    if assign_to is not None:
        with SessionLocal() as db:
            assign(db, uuid.UUID(assign_to), uuid.UUID(res.json()["id"]))
            db.commit()
    return res.json()
