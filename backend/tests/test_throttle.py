"""8단계: 로그인·초대 코드 시도 횟수 제한, 운영 설정 확인"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.models import AuthFailure
from app.retention import purge
from tests.helpers import PASSWORD, signup


def _login(client: TestClient, login_id: str, password: str) -> int:
    return client.post("/auth/login", json={"login_id": login_id, "password": password}).status_code


def test_login_locks_after_failures_and_unlocks_after_window(
    client: TestClient, db: Session
) -> None:
    signup(client)
    client.post("/auth/logout")
    for _ in range(settings.login_max_failures):
        assert _login(client, "carer01", "wrong-pass-1") == 401
    # 막힌 뒤에는 맞는 비밀번호도 막는다
    res = client.post("/auth/login", json={"login_id": "carer01", "password": PASSWORD})
    assert res.status_code == 429 and "15분" in res.json()["detail"]

    # 시간이 지나면 다시 된다
    db.execute(update(AuthFailure).values(created_at=datetime.now(UTC) - timedelta(minutes=16)))
    db.commit()
    assert _login(client, "carer01", PASSWORD) == 200
    # 성공하면 실패 기록을 지운다
    assert db.scalar(select(func.count()).select_from(AuthFailure)) == 0


def test_unknown_login_is_throttled_the_same_way(client: TestClient) -> None:
    """막히는지로 아이디가 있는지 알 수 없게, 없는 아이디도 같이 센다"""
    for _ in range(settings.login_max_failures):
        assert _login(client, "nobody01", "whatever-1") == 401
    assert _login(client, "nobody01", "whatever-1") == 429
    assert _login(client, "someone2", "whatever-1") == 401  # 다른 아이디는 영향 없음


def test_invite_failures_are_capped(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "invite_max_failures_per_hour", 3)
    body = {"password": PASSWORD, "display_name": "x", "invite_code": "ZZZZZ-ZZZZZ"}
    for n in range(3):
        res = client.post("/auth/signup", json={**body, "login_id": f"guess0{n}"})
        assert res.status_code == 400
    res = client.post("/auth/signup", json={**body, "login_id": "guess09"})
    assert res.status_code == 429


def test_purge_removes_old_failures(db: Session) -> None:
    db.add_all(
        [
            AuthFailure(kind="login", key="a", created_at=datetime.now(UTC) - timedelta(days=2)),
            AuthFailure(kind="login", key="b"),
        ]
    )
    db.commit()
    purge(db, datetime.now(UTC))
    assert db.scalars(select(AuthFailure.key)).all() == ["b"]


def test_production_settings_refuse_unsafe_values() -> None:
    with pytest.raises(ValidationError) as e:
        Settings(
            env="production",
            jwt_secret="change-me-to-a-random-string-of-32-chars",
            storage_key=None,  # 테스트 환경변수에 있는 키를 덮어쓴다
            ai_provider="fake",
        )
    message = str(e.value)
    for expected in ("COOKIE_SECURE", "JWT_SECRET", "STORAGE_KEY", "fake"):
        assert expected in message
    ok = Settings(
        env="production",
        jwt_secret="x" * 40,
        cookie_secure=True,
        storage_key="k",
        ai_provider="gemini",
        gemini_api_key="g",
    )
    assert ok.env == "production"
