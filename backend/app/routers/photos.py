"""기록 사진: 확정 전 검토 화면에서 붙이고(최대 3장), 직원만 본다. 보호자에게는 보내지 않는다."""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, UploadFile, status

from app import storage
from app.access import CaregiverUser, StaffUser, record_for_staff, require_health_consent
from app.config import settings
from app.deps import DbSession
from app.models import RecordPhoto
from app.photos import BadImage, clean_jpeg
from app.schemas import PhotoOut

router = APIRouter(prefix="/records", tags=["photos"])

_CHUNK = 1024 * 1024
_NOT_FOUND = "사진을 찾을 수 없습니다"
_EDITABLE = ("draft_ready", "failed")
_ONLY_BEFORE_CONFIRM = "사진은 확정 전 검토 화면에서만 붙일 수 있습니다"


@router.post("/{record_id}/photos", status_code=status.HTTP_201_CREATED, response_model=PhotoOut)
def add_photo(
    record_id: uuid.UUID, photo: UploadFile, db: DbSession, user: CaregiverUser
) -> RecordPhoto:
    record = record_for_staff(db, user, record_id, own=True, for_update=True)
    # 사진은 새로 모으는 건강정보라 업로드·확정·정정과 같이 동의가 있어야 한다
    # (이미 붙인 사진 열람은 3단계 규칙대로 철회 뒤에도 유지)
    require_health_consent(db, record.recipient_id)
    if record.status not in _EDITABLE:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "사진은 확정 전 검토 화면에서만 붙일 수 있습니다"
        )
    if len(record.photos) >= settings.max_photos_per_record:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"사진은 기록당 {settings.max_photos_per_record}장까지입니다"
        )
    data = bytearray()
    while chunk := photo.file.read(_CHUNK):
        data += chunk
        if len(data) > settings.max_photo_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "사진 파일이 너무 큽니다")
    try:
        cleaned = clean_jpeg(bytes(data))
    except BadImage:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "사진으로 읽을 수 없는 파일입니다"
        ) from None
    # 음성과 같은 저장 폴더 아래 photos/ (둘 다 암호화)
    path = storage.write(settings.audio_dir / "photos", str(record.id), cleaned)
    row = RecordPhoto(record_id=record.id, path=str(path), created_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _photo(record_photos: list[RecordPhoto], photo_id: uuid.UUID) -> RecordPhoto:
    found = next((p for p in record_photos if p.id == photo_id), None)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return found


@router.get("/{record_id}/photos/{photo_id}")
def get_photo(
    record_id: uuid.UUID, photo_id: uuid.UUID, db: DbSession, user: StaffUser
) -> Response:
    record = record_for_staff(db, user, record_id)  # 확정 전에는 작성자만
    found = _photo(record.photos, photo_id)
    if found.path is None or not Path(found.path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return Response(
        storage.read(Path(found.path)),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/{record_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    record_id: uuid.UUID, photo_id: uuid.UUID, db: DbSession, user: CaregiverUser
) -> None:
    record = record_for_staff(db, user, record_id, own=True, for_update=True)
    if record.status not in _EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "확정된 기록의 사진은 지울 수 없습니다")
    found = _photo(record.photos, photo_id)
    path = found.path
    db.delete(found)
    db.commit()
    storage.delete(path)
