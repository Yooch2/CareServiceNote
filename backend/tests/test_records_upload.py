import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.main import app
from app.models import VisitRecord
from tests.helpers import add_recipient, put_audio, signup


@pytest.fixture
def other_client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_put_creates_then_is_idempotent(client: TestClient, db: Session) -> None:
    signup(client)
    recipient = add_recipient(client)
    record_id = str(uuid.uuid4())

    first = put_audio(client, record_id, recipient["id"])
    assert first.status_code == 201
    body = first.json()
    assert body["id"] == record_id
    assert body["status"] == "queued"
    assert body["has_audio"] is True

    again = put_audio(client, record_id, recipient["id"], content=b"different")
    assert again.status_code == 200
    assert again.json()["id"] == record_id

    record = db.get(VisitRecord, uuid.UUID(record_id))
    assert record is not None and record.audio_path is not None
    assert Path(record.audio_path).read_bytes() == b"fake-audio"
    assert len(list(settings.audio_dir.glob(f"{record_id}*"))) == 1


def test_put_same_id_by_other_user_conflicts(client: TestClient, other_client: TestClient) -> None:
    signup(client)
    recipient = add_recipient(client)
    record_id = str(uuid.uuid4())
    assert put_audio(client, record_id, recipient["id"]).status_code == 201

    signup(other_client, login_id="carer99")
    assert put_audio(other_client, record_id, recipient["id"]).status_code == 409


def test_put_validation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    signup(client)
    rid = add_recipient(client)["id"]
    assert put_audio(client, str(uuid.uuid4()), rid, content_type="video/mp4").status_code == 415
    assert put_audio(client, str(uuid.uuid4()), rid, content=b"").status_code == 422
    assert put_audio(client, str(uuid.uuid4()), str(uuid.uuid4())).status_code == 404
    ok = put_audio(client, str(uuid.uuid4()), rid, content_type="audio/webm;codecs=opus")
    assert ok.status_code == 201

    monkeypatch.setattr(settings, "max_audio_bytes", 5)
    assert put_audio(client, str(uuid.uuid4()), rid, content=b"123456").status_code == 413


def test_daily_limits(
    client: TestClient, other_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client)
    rid = add_recipient(client)["id"]
    monkeypatch.setattr(settings, "daily_records_per_user", 1)
    assert put_audio(client, str(uuid.uuid4()), rid).status_code == 201
    assert put_audio(client, str(uuid.uuid4()), rid).status_code == 429

    monkeypatch.setattr(settings, "daily_records_per_user", 100)
    monkeypatch.setattr(settings, "daily_records_total", 1)
    signup(other_client, login_id="carer99")
    assert put_audio(other_client, str(uuid.uuid4()), rid).status_code == 429


def test_record_visibility(client: TestClient, other_client: TestClient, db: Session) -> None:
    signup(client)
    rid = add_recipient(client)["id"]
    record_id = str(uuid.uuid4())
    put_audio(client, record_id, rid)

    assert client.get(f"/records/{record_id}").status_code == 200
    audio = client.get(f"/records/{record_id}/audio")
    assert audio.status_code == 200
    assert audio.content == b"fake-audio"
    assert audio.headers["content-type"].startswith("audio/webm")

    signup(other_client, login_id="carer99")
    assert other_client.get(f"/records/{record_id}").status_code == 404
    assert other_client.get(f"/records/{record_id}/audio").status_code == 404
    assert other_client.get(f"/recipients/{rid}/records").json() == []

    record = db.get(VisitRecord, uuid.UUID(record_id))
    assert record is not None
    record.status = "confirmed"
    db.commit()
    assert other_client.get(f"/records/{record_id}").status_code == 200
    assert other_client.get(f"/records/{record_id}/audio").status_code == 404
    summaries = other_client.get(f"/recipients/{rid}/records").json()
    assert [(s["id"], s["is_mine"]) for s in summaries] == [(record_id, False)]
    mine = client.get(f"/recipients/{rid}/records").json()
    assert mine[0]["is_mine"] is True


def test_oversized_body_rejected_before_parsing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client)
    rid = add_recipient(client)["id"]
    monkeypatch.setattr(settings, "max_audio_bytes", 5)
    record_id = str(uuid.uuid4())
    res = put_audio(client, record_id, rid, content=b"x" * 200_000)
    assert res.status_code == 413
    assert res.json()["detail"] == "요청 본문이 너무 큽니다"
    assert list(settings.audio_dir.glob(f"{record_id}*")) == []


def test_chunked_upload_without_length_rejected(client: TestClient) -> None:
    signup(client)
    res = client.put(
        f"/records/{uuid.uuid4()}",
        content=iter([b"--x\r\n"]),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )
    assert res.status_code == 411


def test_daily_limit_holds_under_concurrency(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    signup(client)
    rid = add_recipient(client)["id"]
    monkeypatch.setattr(settings, "daily_records_per_user", 1)
    cookies = dict(client.cookies)

    def upload(_: int) -> int:
        with TestClient(app, cookies=cookies) as c:
            return put_audio(c, str(uuid.uuid4()), rid).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        codes = sorted(pool.map(upload, range(5)))
    assert codes == [201, 429, 429, 429, 429]
