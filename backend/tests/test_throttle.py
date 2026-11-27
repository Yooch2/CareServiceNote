"""8단계: 로그인·초대 코드 시도 횟수 제한, 운영 설정 확인"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings, settings
from app.main import app
from app.models import AuthFailure
from app.retention import purge
from tests.helpers import PASSWORD, signup, signup_center


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
    before = db.scalar(select(func.count()).select_from(AuthFailure))
    assert _login(client, "carer01", PASSWORD) == 200
    # 성공한 시도는 미리 남긴 기록(아이디+IP, IP 두 줄)을 지우고, 지난 실패는 기간이 지나면 사라진다
    assert db.scalar(select(func.count()).select_from(AuthFailure)) == before


def test_unknown_login_is_throttled_the_same_way(client: TestClient) -> None:
    """막히는지로 아이디가 있는지 알 수 없게, 없는 아이디도 같이 센다"""
    for _ in range(settings.login_max_failures):
        assert _login(client, "nobody01", "whatever-1") == 401
    assert _login(client, "nobody01", "whatever-1") == 429
    assert _login(client, "someone2", "whatever-1") == 401  # 다른 아이디는 영향 없음


def test_lock_is_per_client_ip_behind_proxy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """다른 네트워크에서 남의 아이디로 실패를 쌓아도 그 사람은 막히지 않는다"""
    monkeypatch.setattr(settings, "trust_proxy", True)
    signup(client)
    client.post("/auth/logout")
    attacker = {"X-Forwarded-For": "203.0.113.9"}
    for _ in range(settings.login_max_failures):
        res = client.post(
            "/auth/login",
            json={"login_id": "carer01", "password": "wrong-pass-1"},
            headers=attacker,
        )
        assert res.status_code == 401
    blocked = client.post(
        "/auth/login", json={"login_id": "carer01", "password": PASSWORD}, headers=attacker
    )
    assert blocked.status_code == 429
    owner = client.post(
        "/auth/login",
        json={"login_id": "carer01", "password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert owner.status_code == 200


def test_forwarded_header_ignored_without_trust_proxy(client: TestClient) -> None:
    """프록시 뒤가 아닐 때(개발) 클라이언트가 보낸 X-Forwarded-For로 제한을 피할 수 없다"""
    for n in range(settings.login_max_failures):
        client.post(
            "/auth/login",
            json={"login_id": "victim01", "password": "x" * 8},
            headers={"X-Forwarded-For": f"10.0.0.{n}"},
        )
    res = client.post("/auth/login", json={"login_id": "victim01", "password": "x" * 8})
    assert res.status_code == 429


def test_invite_failures_are_capped_per_ip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "invite_max_failures_per_hour", 3)
    monkeypatch.setattr(settings, "trust_proxy", True)
    body = {"password": PASSWORD, "display_name": "x", "invite_code": "ZZZZZ-ZZZZZ"}
    guesser = {"X-Forwarded-For": "203.0.113.9"}
    for n in range(3):
        res = client.post("/auth/signup", json={**body, "login_id": f"guess0{n}"}, headers=guesser)
        assert res.status_code == 400
    res = client.post("/auth/signup", json={**body, "login_id": "guess09"}, headers=guesser)
    assert res.status_code == 429
    # 다른 사람은 올바른 코드로 가입할 수 있다 (전체를 막지 않음)
    signup_center(client, login_id="boss01")
    code = client.post("/org/invites", json={"role": "caregiver"}).json()["code"]
    other = TestClient(app)
    ok = other.post(
        "/auth/signup",
        json={**body, "login_id": "newbie01", "invite_code": code},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert ok.status_code == 201


def test_concurrent_failures_cannot_exceed_limit(client: TestClient) -> None:
    """확인과 기록을 한 잠금 안에서 하므로 동시에 보내도 한도를 넘지 못한다"""
    results: list[int] = []

    def attempt() -> None:
        results.append(_login(TestClient(app), "racer01", "wrong-pass-1"))

    threads = [threading.Thread(target=attempt) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(401) == settings.login_max_failures
    assert results.count(429) == 12 - settings.login_max_failures


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


def test_account_ceiling_across_ips(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """여러 IP로 나눠 같은 아이디를 대입하는 경우 IP와 상관없는 아이디별 상한에 걸린다"""
    monkeypatch.setattr(settings, "trust_proxy", True)
    monkeypatch.setattr(settings, "login_max_failures_per_account", 4)
    for n in range(4):
        res = client.post(
            "/auth/login",
            json={"login_id": "target01", "password": "wrong-pass-1"},
            headers={"X-Forwarded-For": f"203.0.113.{n}"},
        )
        assert res.status_code == 401
    res = client.post(
        "/auth/login",
        json={"login_id": "target01", "password": "wrong-pass-1"},
        headers={"X-Forwarded-For": "203.0.113.99"},
    )
    assert res.status_code == 429


def test_ipv6_grouped_by_64() -> None:
    from app.throttle import _ip_bucket

    assert _ip_bucket("2001:db8:1:2:aaaa::1") == _ip_bucket("2001:db8:1:2:bbbb::9")
    assert _ip_bucket("2001:db8:1:2::1") != _ip_bucket("2001:db8:1:3::1")
    assert _ip_bucket("203.0.113.5") == "203.0.113.5"
