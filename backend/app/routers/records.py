import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import AwareDatetime
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audio_store
from app.access import (
    CaregiverUser,
    ManagerUser,
    StaffUser,
    recipient_for_staff,
    record_for_staff,
    require_health_consent,
)
from app.alerts import evaluate_alerts
from app.audit import audit
from app.config import settings
from app.confirm import ConfirmError, build_confirmed_items, build_followup_checks
from app.deps import DbSession
from app.models import FollowupCheck, RecordItem, User, VisitRecord
from app.schemas import ConfirmIn, RecordOut

router = APIRouter(prefix="/records", tags=["records"])

_UPLOAD_LOCK_KEY = 7_301_001  # 업로드 한도 확인용 advisory lock 번호


def _existing_or_conflict(record: VisitRecord, user: User, recipient_id: uuid.UUID) -> VisitRecord:
    if record.caregiver_id != user.id or record.recipient_id != recipient_id:
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
    user: CaregiverUser,
    db: DbSession,
    response: Response,
) -> VisitRecord:
    # 배정이 해제됐으면 재전송이라도 404 (기존 기록 내용을 돌려주지 않는다)
    recipient_for_staff(db, user, recipient_id)
    existing = db.get(VisitRecord, record_id)
    if existing is not None:
        return _existing_or_conflict(existing, user, recipient_id)
    require_health_consent(db, recipient_id)

    ext = audio_store.extension_for(audio.content_type)
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "지원하지 않는 음성 형식입니다")

    try:
        path = audio_store.save(record_id, audio.file, ext)
    except audio_store.AudioTooLarge:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "음성 파일이 너무 큽니다") from None
    except audio_store.AudioEmpty:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "빈 음성 파일입니다") from None

    # 한도 확인과 저장을 한 번에: 잠금은 커밋·롤백 때 풀린다
    # ponytail: 업로드 전체를 잠그는 전역 잠금.
    # 동시 업로드가 많아지면 사용자별 잠금 + 전체 카운터 행으로 바꾼다.
    try:
        db.execute(select(func.pg_advisory_xact_lock(_UPLOAD_LOCK_KEY)))
        _check_daily_limits(db, user)
    except HTTPException:
        db.rollback()
        audio_store.delete(str(path))
        raise

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
        return _existing_or_conflict(winner, user, recipient_id)
    db.refresh(record)
    response.status_code = status.HTTP_201_CREATED
    return record


@router.get("/{record_id}", response_model=RecordOut)
def get_record(record_id: uuid.UUID, user: StaffUser, db: DbSession) -> VisitRecord:
    record = record_for_staff(db, user, record_id)
    audit(db, user, "view_record", record.recipient_id, record.id)
    return record


@router.get("/{record_id}/audio")
def get_audio(record_id: uuid.UUID, user: CaregiverUser, db: DbSession) -> FileResponse:
    record = record_for_staff(db, user, record_id, own=True)
    if record.audio_path is None or not Path(record.audio_path).exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "음성 파일이 없습니다")
    path = Path(record.audio_path)
    media_type = audio_store.MEDIA_TYPES.get(path.suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.post("/{record_id}/confirm", response_model=RecordOut)
def confirm_record(
    record_id: uuid.UUID, body: ConfirmIn, user: CaregiverUser, db: DbSession
) -> VisitRecord:
    record = record_for_staff(db, user, record_id, own=True, for_update=True)
    require_health_consent(db, record.recipient_id)
    if record.status not in ("draft_ready", "failed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "지금은 확정할 수 없는 상태입니다")
    draft = record.draft or {}
    try:
        values = build_confirmed_items(draft.get("items", []), body)
        checks = build_followup_checks(draft, body)
    except ConfirmError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    _ensure_open_followups(db, record, [c["followup_item_id"] for c in checks])

    old_audio = record.audio_path
    record.items = [RecordItem(**v) for v in values]
    record.followup_checks = [FollowupCheck(**c) for c in checks]
    record.status = "confirmed"
    record.confirmed_at = datetime.now(UTC)
    record.meal_level, record.mood = body.meal_level, body.mood
    record.audio_path = None
    try:
        db.flush()
        evaluate_alerts(db, record)
        db.commit()
    except IntegrityError:
        # 다른 기록이 같은 확인 사항을 먼저 확정한 경우 (followup_item_id unique)
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, _ALREADY_CHECKED) from None
    audio_store.delete(old_audio)
    return record


_ALREADY_CHECKED = "이미 다른 기록에서 확인된 항목입니다. 새로고침해 주세요"


@router.post("/{record_id}/review", response_model=RecordOut)
def review_record(record_id: uuid.UUID, user: ManagerUser, db: DbSession) -> VisitRecord:
    """센터 확인 서명. 확정 기록에 한 번만 남긴다."""
    record = record_for_staff(db, user, record_id, for_update=True)
    if record.reviewed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 확인 서명한 기록입니다")
    record.reviewed_by, record.reviewed_at = user.id, datetime.now(UTC)
    db.commit()
    db.refresh(record, ["reviewer"])
    return record


def _ensure_open_followups(db: Session, record: VisitRecord, item_ids: list[uuid.UUID]) -> None:
    """확인 결과를 남길 항목이 이 수급자의 확정된 '다음 확인' 항목이고 아직 확인 전인지 본다."""
    if not item_ids:
        return
    rows = db.execute(
        select(RecordItem.id, FollowupCheck.id)
        .join(VisitRecord, RecordItem.record_id == VisitRecord.id)
        .outerjoin(FollowupCheck, FollowupCheck.followup_item_id == RecordItem.id)
        .where(
            RecordItem.id.in_(item_ids),
            RecordItem.category == "followup",
            VisitRecord.status == "confirmed",
            VisitRecord.recipient_id == record.recipient_id,
        )
    ).all()
    if len(rows) != len(set(item_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "확인할 수 없는 항목입니다")
    if any(check_id is not None for _, check_id in rows):
        raise HTTPException(status.HTTP_409_CONFLICT, _ALREADY_CHECKED)
