import uuid

from fastapi.testclient import TestClient

from tests.helpers import add_recipient, signup


def test_requires_login(client: TestClient) -> None:
    assert client.get("/recipients").status_code == 401
    assert client.post("/recipients", json={"name": "가상"}).status_code == 401


def test_create_list_get(client: TestClient) -> None:
    signup(client)
    first = add_recipient(client, "  가상수급자A  ")
    add_recipient(client, "가상수급자B")
    assert first["name"] == "가상수급자A"

    listed = client.get("/recipients").json()
    assert [r["name"] for r in listed] == ["가상수급자A", "가상수급자B"]

    got = client.get(f"/recipients/{first['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == first["id"]


def test_not_found_does_not_echo_input(client: TestClient) -> None:
    signup(client)
    missing = uuid.uuid4()
    res = client.get(f"/recipients/{missing}")
    assert res.status_code == 404
    assert str(missing) not in res.text


def test_name_validation(client: TestClient) -> None:
    signup(client)
    assert client.post("/recipients", json={"name": "  "}).status_code == 422
    assert client.post("/recipients", json={"name": "가" * 31}).status_code == 422
