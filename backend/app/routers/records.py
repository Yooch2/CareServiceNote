import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import AwareDatetime
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audio_store
from app.config import settings
from app.deps import CurrentUser, DbSession
from app.models import User, VisitRecord
from app.routers.recipients import get_recipient_or_404
from app.schemas import RecordOut

router = APIRouter(prefix="/records", tags=["records"])

_NOT_FOUND = "기록을 찾을 수 없습니다"


def load_own_record(
    db: Session, record_id: uuid.UUID, user: User, *, for_update: bool = False
) -> VisitRecord:
    stmt = select(VisitRecord).where(VisitRecord.id == record_id)
    if for_update:
        stmt = stmt.with_for_update()
    record = db.scalar(stmt)
    if record is None or record.caregiver_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return record


def _existing_or_conflict(record: VisitRecord, user: User) -> VisitRecord:
    if record.caregiver_id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용된 기록 ID입니다")
    return record


def _check_daily_limits(db: Session, user: User) -> None:
    since = func.now() - timedelta(days=1)
    base = select(func.count()).select_from(VisitRecord).where(VisitRecord.created_at > since)
    mine = db.scalar(base.where(VisitRecord.caregiver_id == user.id)) or 0
    if mine >= settings.daily_records_per_user:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "오늘 기록할 수 있는 횟수를 넘었습니다"
        )
    total = db.scalar(base) or 0
    if total >= settings.daily_records_total:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "오늘 서비스 전체 기록 한도를 넘었습니다"
        )


@router.put("/{record_id}", response_model=RecordOut)
def put_record(
    record_id: uuid.UUID,
    audio: UploadFile,
    recipient_id: Annotated[uuid.UUID, Form()],
    visited_on: Annotated[date, Form()],
    recorded_at: Annotated[AwareDatetime, Form()],
    user: CurrentUser,
    db: DbSession,
    response: Response,
) -> VisitRecord:
    existing = db.get(VisitRecord, record_id)
    if existing is not None:
        return _existing_or_conflict(existing, user)

    ext = audio_store.extension_for(audio.content_type)
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "지원하지 않는 음성 형식입니다")
    get_recipient_or_404(db, recipient_id)
    _check_daily_limits(db, user)

    try:
        path = audio_store.save(record_id, audio.file, ext)
    except audio_store.AudioTooLarge:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "음성 파일이 너무 큽니다") from None
    except audio_store.AudioEmpty:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "빈 음성 파일입니다") from None

    record = VisitRecord(
        id=record_id,
        recipient_id=recipient_id,
        caregiver_id=user.id,
        visited_on=visited_on,
        recorded_at=recorded_at,
        status="queued",
        audio_path=str(path),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # 같은 id가 동시에 들어온 경우: 먼저 저장된 쪽을 기준으로 응답
        db.rollback()
        audio_store.delete(str(path))
        winner = db.get(VisitRecord, record_id)
        if winner is None:
            raise
        return _existing_or_conflict(winner, user)
    db.refresh(record)
    response.status_code = status.HTTP_201_CREATED
    return record


@router.get("/{record_id}", response_model=RecordOut)
def get_record(record_id: uuid.UUID, user: CurrentUser, db: DbSession) -> VisitRecord:
    record = db.get(VisitRecord, record_id)
    if record is None or (record.status != "confirmed" and record.caregiver_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, _NOT_FOUND)
    return record


@router.get("/{record_id}/audio")
def get_audio(record_id: uuid.UUID, user: CurrentUser, db: DbSession) -> FileResponse:
    record = load_own_record(db, record_id, user)
    if record.audio_path is None or not Path(record.audio_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "음성 파일이 없습니다")
    path = Path(record.audio_path)
    media_type = audio_store.MEDIA_TYPES.get(path.suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type)
