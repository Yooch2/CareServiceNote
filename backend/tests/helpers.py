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
