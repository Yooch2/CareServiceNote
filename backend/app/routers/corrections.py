"""6단계: 확정 기록 정정(사유·이력·재평가), 감사 로그 조회, 내보내기"""

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select

from app.access import ManagedRecipient, StaffUser, record_for_staff
from app.alerts import reevaluate_after_correction
from app.audit import audit
from app.deps import DbSession
from app.models import (
    AuditEvent,
    FollowupCheck,
    GuardianSummary,
    RecordItem,
    RecordRevision,
    User,
    VisitRecord,
)
from app.schemas import AuditOut, ItemCorrectionIn, RecordOut, StateCorrectionIn

router = APIRouter(tags=["corrections"])

AUDIT_LIMIT = 100
_NOT_CONFIRMED = "확정된 기록만 정정할 수 있습니다"
_NOT_AUTHOR = "다른 요양보호사의 기록은 작성자나 기관 담당자가 정정합니다"
_NO_CHANGE = "바뀐 내용이 없습니다"


def _correctable(db: DbSession, user: User, record_id: uuid.UUID) -> VisitRecord:
    """작성자(지금 배정 중)나 같은 센터 기관 담당자만, 확정 기록만"""
    record = record_for_staff(db, user, record_id, for_update=True)
    if record.status != "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, _NOT_CONFIRMED)
    if user.role == "caregiver" and record.caregiver_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, _NOT_AUTHOR)
    return record


def _after_correction(
    db: DbSession, user: User, record: VisitRecord, item_id: uuid.UUID | None
) -> None:
    """센터 확인 서명 초기화, 정정 항목을 근거로 쓴 승인 요약은 승인 취소, 알림 재평가, 감사 로그"""
    record.reviewed_by = record.reviewed_at = None
    if item_id is not None:
        summary = db.scalar(
            select(GuardianSummary).where(GuardianSummary.record_id == record.id).with_for_update()
        )
        if (
            summary is not None
            and summary.status == "approved"
            and any(str(item_id) in s["item_ids"] for s in summary.sentences)
        ):
            summary.status, summary.approved_by, summary.approved_at = "draft", None, None
    db.flush()
    reevaluate_after_correction(db, record)
    audit(db, user, "correct", record.recipient_id, record.id, commit=False)
    db.commit()
    db.refresh(record, ["revisions", "reviewer", "items"])


def _item_values(item: RecordItem) -> dict[str, Any]:
    return {
        "category": item.category,
        "content": item.content,
        "body_part": item.body_part,
        "risk_tag": item.risk_tag,
    }


@router.patch("/records/{record_id}/items/{item_id}", response_model=RecordOut)
def correct_item(
    record_id: uuid.UUID,
    item_id: uuid.UUID,
    body: ItemCorrectionIn,
    db: DbSession,
    user: StaffUser,
) -> VisitRecord:
    record = _correctable(db, user, record_id)
    item = next((i for i in record.items if i.id == item_id), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "항목을 찾을 수 없습니다")
    before = _item_values(item)
    after = body.model_dump(exclude={"reason"})
    if before == after:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _NO_CHANGE)
    if item.category == "followup" and after["category"] != "followup" and item.check is not None:
        # 이미 이후 방문에서 확인된 '다음 확인'은 분류를 바꾸면 확인 결과가 가리킬 곳이 사라진다
        raise HTTPException(
            status.HTTP_409_CONFLICT, "이미 확인된 '다음 확인' 항목은 분류를 바꿀 수 없습니다"
        )
    for key, value in after.items():
        setattr(item, key, value)
    db.add(
        RecordRevision(
            record_id=record.id,
            item_id=item.id,
            before=before,
            after=after,
            reason=body.reason,
            user_id=user.id,
        )
    )
    _after_correction(db, user, record, item.id)
    return record


@router.patch("/records/{record_id}/state", response_model=RecordOut)
def correct_state(
    record_id: uuid.UUID, body: StateCorrectionIn, db: DbSession, user: StaffUser
) -> VisitRecord:
    record = _correctable(db, user, record_id)
    before = {"meal_level": record.meal_level, "mood": record.mood}
    after = {"meal_level": body.meal_level, "mood": body.mood}
    if before == after:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, _NO_CHANGE)
    record.meal_level, record.mood = body.meal_level, body.mood
    db.add(
        RecordRevision(
            record_id=record.id, before=before, after=after, reason=body.reason, user_id=user.id
        )
    )
    _after_correction(db, user, record, None)
    return record


@router.get("/recipients/{recipient_id}/audit", response_model=list[AuditOut])
def audit_log(recipient: ManagedRecipient, db: DbSession) -> list[AuditOut]:
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.recipient_id == recipient.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(AUDIT_LIMIT)
    )
    return [
        AuditOut.model_validate(
            {
                "id": e.id,
                "actor_name": e.actor.display_name,
                "actor_role": e.actor.role,
                "action": e.action,
                "record_id": e.record_id,
                "created_at": e.created_at,
            }
        )
        for e in rows
    ]


_CATEGORY_KO = {"remark": "말씀", "observation": "관찰", "followup": "다음 확인"}
_ORIGIN_KO = {"ai": "AI 초안 그대로", "ai_edited": "AI 초안 수정", "human": "직접 작성"}
_MEAL_KO = ("거의 못 드심", "조금", "절반", "대부분", "다 드심")
_MOOD_KO = {"good": "좋음", "neutral": "보통", "low": "처짐"}
_HEADER = (
    "방문일", "분류", "내용", "근거", "출처",
    "정정", "확인 결과", "식사량", "기분", "센터 확인",
)  # fmt: skip


@router.get("/recipients/{recipient_id}/export")
def export_records(recipient: ManagedRecipient, db: DbSession, user: StaffUser) -> Response:
    """확정 기록 CSV. 엑셀에서 한글이 깨지지 않게 UTF-8 BOM을 붙인다.

    파일 이름에 수급자 이름은 넣지 않는다.
    """
    records = db.scalars(
        select(VisitRecord)
        .where(VisitRecord.recipient_id == recipient.id, VisitRecord.status == "confirmed")
        .order_by(VisitRecord.visited_on, VisitRecord.created_at)
    ).all()
    checks = {
        c.followup_item_id: c
        for c in db.scalars(
            select(FollowupCheck).where(FollowupCheck.record_id.in_([r.id for r in records]))
        )
    }
    corrected = {rev.item_id for r in records for rev in r.revisions if rev.item_id is not None}
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "방문일",
            "분류",
            "내용",
            "근거",
            "출처",
            "정정",
            "확인 결과",
            "식사량",
            "기분",
            "센터 확인",
        ]
    )
    for r in records:
        meal = _MEAL_KO[r.meal_level] if r.meal_level is not None else ""
        mood = _MOOD_KO.get(r.mood or "", "")
        for item in r.items:
            check = checks.get(item.id) or item.check
            writer.writerow(
                [
                    r.visited_on.isoformat(),
                    _CATEGORY_KO[item.category],
                    item.content,
                    item.evidence or "",
                    _ORIGIN_KO[item.origin],
                    "예" if item.id in corrected else "",
                    check.result if check else "",
                    meal,
                    mood,
                    r.reviewed_at.date().isoformat() if r.reviewed_at else "",
                ]
            )
    audit(db, user, "export", recipient.id)
    return Response(
        content="﻿" + out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="records-{recipient.id}.csv"'},
    )
