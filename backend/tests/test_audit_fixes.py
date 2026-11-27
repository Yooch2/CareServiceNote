"""전체 보안 점검에서 나온 것.

보호자 요약 동의, 센터 만들기 제한, 미확정 전사문 보관, 로그아웃 토큰, 분류 직전 동의, CSRF
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import worker
from app.ai.fake import FakeClassifier, FakeTranscriber
from app.config import settings
from app.db import SessionLocal
from app.deps import SESSION_COOKIE
from app.models import Consent, VisitRecord
from app.retention import purge
from tests.helpers import PASSWORD, make_confirmed, make_record, signup, signup_center


def test_guardian_summary_needs_health_consent(client: TestClient, db: Session) -> None:
    signup_center(client)
    rid = client.post("/recipients", json={"name": "가상수급자"}).json()["id"]
    client.post(
        f"/recipients/{rid}/consents", json={"kind": "guardian_share", "granted_on": "2026-11-01"}
    )
    record = make_confirmed(db, [("remark", "산책")], recipient_id=uuid.UUID(rid))
    res = client.post(f"/records/{record.id}/guardian-summary")
    assert res.status_code == 409 and "건강정보" in res.json()["detail"]


def test_center_signup_is_limited_per_ip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "signup_max_per_ip_per_hour", 2)
    body = {"password": PASSWORD, "display_name": "x", "center_name": "c"}
    for n in range(2):
        assert (
            client.post("/auth/signup", json={**body, "login_id": f"boss0{n}"}).status_code == 201
        )
    assert client.post("/auth/signup", json={**body, "login_id": "boss09"}).status_code == 429


def test_purge_clears_texts_of_old_unconfirmed_records(db: Session) -> None:
    old = make_record(db, status="failed", transcript="오래된 미확정 전사문")
    old.draft = {"items": []}
    old.created_at = datetime.now(UTC) - timedelta(days=settings.audio_retention_days + 1)
    fresh = make_record(db, status="draft_ready", transcript="최근 초안")
    db.commit()
    purge(db, datetime.now(UTC))
    db.expire_all()
    stale = db.get(VisitRecord, old.id)
    assert stale is not None and stale.transcript is None and stale.draft is None
    assert db.get(VisitRecord, fresh.id).transcript == "최근 초안"  # type: ignore[union-attr]


def test_logout_invalidates_copied_token(client: TestClient) -> None:
    signup(client)
    copied = client.cookies.get(SESSION_COOKIE)
    assert copied
    client.post("/auth/logout")
    thief = TestClient(client.app)
    thief.cookies.set(SESSION_COOKIE, copied)
    assert thief.get("/auth/me").status_code == 401
    # 다시 로그인하면 새 토큰은 된다
    assert (
        client.post("/auth/login", json={"login_id": "carer01", "password": PASSWORD}).status_code
        == 200
    )
    assert client.get("/auth/me").status_code == 200


def test_consent_withdrawn_during_transcription_stops_classification(db: Session) -> None:
    record = make_record(db)

    class WithdrawWhileTranscribing(FakeTranscriber):
        def transcribe(self, audio):  # noqa: ANN001, ANN201
            with SessionLocal() as s:
                for c in s.scalars(
                    select(Consent).where(Consent.recipient_id == record.recipient_id)
                ):
                    c.withdrawn_at = datetime.now(UTC)
                s.commit()
            return super().transcribe(audio)

    classifier = FakeClassifier()
    worker.run_once(
        SessionLocal,
        WithdrawWhileTranscribing(),
        classifier,
        lambda: datetime.now(UTC) + timedelta(days=1),
    )
    db.refresh(record)
    assert record.status == "failed" and record.error_code == "consent_withdrawn"
    assert classifier.calls == 0


def test_cross_site_state_change_is_rejected(client: TestClient) -> None:
    body = {"login_id": "x", "password": "y"}
    res = client.post("/auth/login", json=body, headers={"Sec-Fetch-Site": "same-site"})
    assert res.status_code == 403
    res = client.post("/auth/login", json=body, headers={"Sec-Fetch-Site": "cross-site"})
    assert res.status_code == 403
    # 같은 출처와 브라우저가 아닌 도구(헤더 없음)는 그대로
    assert (
        client.post("/auth/login", json=body, headers={"Sec-Fetch-Site": "same-origin"}).status_code
        == 401
    )
    assert client.post("/auth/login", json=body).status_code == 401
    # 읽기 요청은 막지 않는다
    assert client.get("/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200
