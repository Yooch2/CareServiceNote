"""6단계 PR②: 보관 기간 삭제, 사진(EXIF 제거·암호화·권한·장수 제한)"""

import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app import storage
from app.config import settings
from app.models import RecordPhoto, VisitRecord
from app.retention import purge
from tests.helpers import (
    add_recipient,
    colleague,
    make_confirmed,
    make_record,
    process_all,
    put_audio,
    signup,
)

NOW = datetime.now(UTC)


def _jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (3000, 2000), (200, 180, 160))
    exif = Image.Exif()
    exif[0x010F] = "가상 카메라"  # Make
    exif[0x8825] = {2: (37.0, 30.0, 0.0), 4: (127.0, 0.0, 0.0)}  # GPSInfo
    out = io.BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def _draft(client: TestClient) -> tuple[str, str]:
    signup(client)
    rid = add_recipient(client)["id"]
    record_id = str(uuid.uuid4())
    put_audio(client, record_id, rid)
    process_all()
    return rid, record_id


def _upload(client: TestClient, record_id: str, data: bytes, ctype: str = "image/jpeg"):  # noqa: ANN202
    return client.post(f"/records/{record_id}/photos", files={"photo": ("p.jpg", data, ctype)})


def test_photo_is_cleaned_encrypted_and_limited(client: TestClient, db: Session) -> None:
    _, record_id = _draft(client)
    res = _upload(client, record_id, _jpeg_with_gps())
    assert res.status_code == 201, res.text
    photo_id = res.json()["id"]

    stored = db.get(RecordPhoto, uuid.UUID(photo_id))
    assert stored is not None and stored.path is not None
    raw = Path(stored.path).read_bytes()
    assert not raw.startswith(b"\xff\xd8")  # 디스크에는 JPEG가 아니라 암호문

    served = client.get(f"/records/{record_id}/photos/{photo_id}")
    assert served.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(served.content)) as img:
        assert max(img.size) == 1600  # 줄임
        assert dict(img.getexif()) == {}  # 위치·기기 정보 없음

    for _ in range(2):
        assert _upload(client, record_id, _jpeg_with_gps()).status_code == 201
    assert _upload(client, record_id, _jpeg_with_gps()).status_code == 409  # 3장까지
    assert len(client.get(f"/records/{record_id}").json()["photos"]) == 3


def test_photo_rejects_non_images_and_large_files(client: TestClient, monkeypatch) -> None:  # noqa: ANN001
    _, record_id = _draft(client)
    assert _upload(client, record_id, b"not an image").status_code == 415
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, format="GIF")
    assert _upload(client, record_id, gif.getvalue(), "image/gif").status_code == 415
    monkeypatch.setattr(settings, "max_photo_bytes", 100)
    assert _upload(client, record_id, _jpeg_with_gps()).status_code == 413


def test_photo_only_before_confirm_and_only_staff(
    client: TestClient, other_client: TestClient
) -> None:
    rid, record_id = _draft(client)
    photo_id = _upload(client, record_id, _jpeg_with_gps()).json()["id"]
    colleague(client, other_client, assign_to=rid)
    # 확정 전에는 작성자만
    assert other_client.get(f"/records/{record_id}/photos/{photo_id}").status_code == 404

    draft = client.get(f"/records/{record_id}").json()["draft"]
    body = {
        "items": [
            {"draft_index": i, "category": it["category"], "content": it["content"]}
            for i, it in enumerate(draft["items"])
        ]
    }
    assert client.post(f"/records/{record_id}/confirm", json=body).status_code == 200
    # 확정 뒤에는 같은 수급자 담당 직원이 볼 수 있고, 붙이거나 지울 수 없다
    assert other_client.get(f"/records/{record_id}/photos/{photo_id}").status_code == 200
    assert _upload(client, record_id, _jpeg_with_gps()).status_code == 409
    assert client.delete(f"/records/{record_id}/photos/{photo_id}").status_code == 409


def test_delete_photo_removes_file(client: TestClient, db: Session) -> None:
    _, record_id = _draft(client)
    photo_id = _upload(client, record_id, _jpeg_with_gps()).json()["id"]
    path = Path(db.get(RecordPhoto, uuid.UUID(photo_id)).path or "")  # type: ignore[union-attr]
    assert client.delete(f"/records/{record_id}/photos/{photo_id}").status_code == 204
    assert not path.exists()
    assert client.get(f"/records/{record_id}").json()["photos"] == []


def test_purge_old_unconfirmed_audio_and_photos(db: Session) -> None:
    old = make_record(db, status="draft_ready")
    fresh = make_record(db, status="draft_ready")
    photo_path = storage.write(settings.audio_dir / "photos", str(old.id), b"jpeg")
    db.add(RecordPhoto(record_id=old.id, path=str(photo_path), created_by=old.caregiver_id))
    old.created_at = NOW - timedelta(days=settings.audio_retention_days + 1)
    db.commit()
    old_audio = Path(old.audio_path or "")

    result = purge(db, NOW)
    assert (result.audio, result.photos) == (1, 1)
    db.expire_all()
    assert db.get(VisitRecord, old.id).audio_path is None  # type: ignore[union-attr]
    assert db.get(VisitRecord, fresh.id).audio_path is not None  # type: ignore[union-attr]
    assert not old_audio.exists() and not photo_path.exists()
    assert purge(db, NOW).audio == 0  # 다시 돌려도 같은 결과


def test_purge_old_transcripts_keeps_items(db: Session) -> None:
    old = make_confirmed(
        db,
        [("remark", "무릎이 불편하다")],
        transcript="오늘 어르신이 무릎이 불편하다고 하셨어요",
        confirmed_at=NOW - timedelta(days=settings.transcript_retention_days + 1),
    )
    recent = make_confirmed(db, [("remark", "산책")], transcript="산책 이야기")
    assert purge(db, NOW).transcripts == 1
    db.expire_all()
    kept = db.get(VisitRecord, old.id)
    assert kept is not None and kept.transcript is None and kept.draft is None
    assert [i.content for i in kept.items] == ["무릎이 불편하다"]  # 공식 기록은 남김
    assert db.get(VisitRecord, recent.id).transcript == "산책 이야기"  # type: ignore[union-attr]
