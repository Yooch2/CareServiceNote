from typing import Any

from fastapi.testclient import TestClient


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
