from fastapi.testclient import TestClient

from app.deps import SESSION_COOKIE
from tests.helpers import signup


def test_signup_sets_cookie_and_me_works(client: TestClient) -> None:
    user = signup(client)
    assert user["login_id"] == "carer01"
    assert "password_hash" not in user
    assert client.cookies.get(SESSION_COOKIE)
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == user["id"]


def test_session_cookie_is_httponly(client: TestClient) -> None:
    res = client.post(
        "/auth/signup",
        json={"login_id": "carer02", "password": "password123", "display_name": "이요양"},
    )
    header = res.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header


def test_signup_duplicate_login_id(client: TestClient) -> None:
    signup(client)
    res = client.post(
        "/auth/signup",
        json={"login_id": "carer01", "password": "password123", "display_name": "다른"},
    )
    assert res.status_code == 409


def test_signup_validation(client: TestClient) -> None:
    for body in (
        {"login_id": "ab", "password": "password123", "display_name": "x"},
        {"login_id": "Upper01", "password": "password123", "display_name": "x"},
        {"login_id": "carer03", "password": "short", "display_name": "x"},
        {"login_id": "carer03", "password": "password123", "display_name": "   "},
    ):
        assert client.post("/auth/signup", json=body).status_code == 422


def test_login_logout(client: TestClient) -> None:
    signup(client)
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401

    bad = client.post("/auth/login", json={"login_id": "carer01", "password": "wrongpass1"})
    assert bad.status_code == 401
    unknown = client.post("/auth/login", json={"login_id": "nobody", "password": "password123"})
    assert unknown.status_code == 401
    assert bad.json()["detail"] == unknown.json()["detail"]

    ok = client.post("/auth/login", json={"login_id": "carer01", "password": "password123"})
    assert ok.status_code == 200
    assert client.get("/auth/me").status_code == 200


def test_invalid_token_rejected(client: TestClient) -> None:
    client.cookies.set(SESSION_COOKIE, "not-a-jwt")
    assert client.get("/auth/me").status_code == 401
