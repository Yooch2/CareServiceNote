"""5단계: 보호자 하루 요약(승인 후 공유), 방문 시작·종료, 업무 메시지"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import (
    CaregiverUser,
    ManagerUser,
    StaffRecipient,
    StaffUser,
    has_consent,
    record_for_staff,
)
from app.ai.errors import AIError, TransientAIError
from app.ai.summary import clean_summary, summarize_for_guardian
from app.ai.types import StructuredLLM
from app.ai_usage import reserve_ai_call
from app.deps import DbSession
from app.models import GuardianSummary, Message, User, VisitRecord, VisitSession
from app.routers.handover import get_llm
from app.schemas import (
    GuardianSummaryEdit,
    GuardianSummaryOut,
    MessageIn,
    MessageOut,
    VisitSessionOut,
)

router = APIRouter(tags=["sharing"])

_CATEGORY_KO = {"remark": "말씀", "observation": "관찰", "followup": "다음 확인"}
GUARDIAN_SUMMARY_SENTENCES = 3
VISIT_DAYS = 7
MESSAGE_LIMIT = 50
_NO_SHARE_CONSENT = "보호자 공유 동의가 없어 요약을 만들 수 없습니다"
_APPROVED = "승인된 요약입니다. 승인을 취소한 뒤 다시 만들어 주세요"
_APPROVED_EDIT = "승인된 요약은 승인을 취소한 뒤 고칠 수 있습니다"
_NO_ADD = "문장을 추가할 수 없습니다. 새로고침해 주세요"
_RACE = "다른 요청이 먼저 요약을 만들었습니다. 새로고침해 주세요"
_AI_BUSY = "AI 요약을 잠시 만들 수 없습니다"
_AI_FAILED = "AI 요약을 만들지 못했습니다"
_OPEN_VISIT = "끝나지 않은 방문이 있습니다. 먼저 방문 종료를 눌러 주세요"


# --- 보호자 하루 요약 ---


def _summary_out(db: Session, record: VisitRecord, summary: GuardianSummary) -> GuardianSummaryOut:
    categories = {str(i.id): i.category for i in record.items}
    approver = db.get(User, summary.approved_by) if summary.approved_by else None
    return GuardianSummaryOut.model_validate(
        {
            "status": summary.status,
            "sentences": [
                {
                    **s,
                    "categories": sorted({categories[i] for i in s["item_ids"] if i in categories}),
                }
                for s in summary.sentences
            ],
            "created_at": summary.created_at,
            "updated_at": summary.updated_at,
            "approved_at": summary.approved_at,
            "approver_name": approver.display_name if approver else None,
        }
    )


def _get_summary(
    db: Session, record_id: uuid.UUID, *, for_update: bool = False
) -> GuardianSummary | None:
    stmt = select(GuardianSummary).where(GuardianSummary.record_id == record_id)
    return db.scalar(stmt.with_for_update() if for_update else stmt)


def _require_summary(db: Session, record_id: uuid.UUID) -> GuardianSummary:
    summary = _get_summary(db, record_id, for_update=True)
    if summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보호자 요약이 없습니다")
    return summary


@router.get("/records/{record_id}/guardian-summary", response_model=GuardianSummaryOut | None)
def get_guardian_summary(
    record_id: uuid.UUID, db: DbSession, user: StaffUser
) -> GuardianSummaryOut | None:
    record = record_for_staff(db, user, record_id)
    summary = _get_summary(db, record.id)
    return _summary_out(db, record, summary) if summary else None


@router.post("/records/{record_id}/guardian-summary", response_model=GuardianSummaryOut)
def create_guardian_summary(
    record_id: uuid.UUID,
    db: DbSession,
    user: ManagerUser,
    llm: Annotated[StructuredLLM, Depends(get_llm)],
) -> GuardianSummaryOut:
    """확정 항목만으로 AI가 보호자용 요약을 쓴다 (전사문은 넣지 않는다).

    승인 전에는 보호자에게 안 보인다.
    """
    record = record_for_staff(db, user, record_id)  # 기관 담당자는 확정 기록만 통과
    if not has_consent(db, record.recipient_id, "guardian_share"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "보호자 공유 동의가 없어 요약을 만들 수 없습니다"
        )
    existing = _get_summary(db, record.id)
    if existing is not None and existing.status == "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "승인된 요약입니다. 승인을 취소한 뒤 다시 만들어 주세요"
        )
    if not record.items:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "요약할 항목이 없습니다")

    refs = {f"I{n}": item for n, item in enumerate(record.items, start=1)}
    lines = [f"{ref}. [{_CATEGORY_KO[i.category]}] {i.content}" for ref, i in refs.items()]
    reserve_ai_call(db, user, "guardian_summary")
    try:
        out = summarize_for_guardian(llm, lines)
        cleaned = clean_summary(out, refs, limit=GUARDIAN_SUMMARY_SENTENCES)
    except TransientAIError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "AI 요약을 잠시 만들 수 없습니다"
        ) from None
    except AIError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, _AI_FAILED) from None
    if not cleaned:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, _AI_FAILED)

    sentences: list[dict[str, Any]] = [
        {"text": text, "item_ids": [str(i.id) for i in items], "edited": False}
        for text, items in cleaned
    ]
    summary = _get_summary(db, record.id, for_update=True)
    if summary is None:
        summary = GuardianSummary(record_id=record.id, sentences=sentences, created_by=user.id)
        db.add(summary)
    elif summary.status == "approved":  # AI를 부르는 동안 다른 사람이 승인함
        raise HTTPException(
            status.HTTP_409_CONFLICT, "승인된 요약입니다. 승인을 취소한 뒤 다시 만들어 주세요"
        )
    else:
        summary.sentences, summary.created_by = sentences, user.id
    try:
        db.commit()
    except IntegrityError:  # 동시에 처음 만든 경우
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "다른 요청이 먼저 요약을 만들었습니다. 새로고침해 주세요"
        ) from None
    db.refresh(summary)
    return _summary_out(db, record, summary)


@router.put("/records/{record_id}/guardian-summary", response_model=GuardianSummaryOut)
def edit_guardian_summary(
    record_id: uuid.UUID, body: GuardianSummaryEdit, db: DbSession, user: ManagerUser
) -> GuardianSummaryOut:
    record = record_for_staff(db, user, record_id)
    summary = _require_summary(db, record.id)
    if summary.status == "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "승인된 요약은 승인을 취소한 뒤 고칠 수 있습니다"
        )
    if len(body.sentences) != len(summary.sentences):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "문장을 추가할 수 없습니다. 새로고침해 주세요"
        )
    summary.sentences = [
        {**old, "text": new.text, "edited": old["edited"] or new.text != old["text"]}
        for old, new in zip(summary.sentences, body.sentences, strict=True)
        if new.text
    ]
    db.commit()
    db.refresh(summary)
    return _summary_out(db, record, summary)


@router.post("/records/{record_id}/guardian-summary/approve", response_model=GuardianSummaryOut)
def approve_guardian_summary(
    record_id: uuid.UUID, db: DbSession, user: ManagerUser
) -> GuardianSummaryOut:
    record = record_for_staff(db, user, record_id)
    summary = _require_summary(db, record.id)
    if not summary.sentences:
        raise HTTPException(status.HTTP_409_CONFLICT, "남은 문장이 없어 승인할 수 없습니다")
    if summary.status != "approved":
        summary.status, summary.approved_by = "approved", user.id
        summary.approved_at = datetime.now(UTC)
        db.commit()
        db.refresh(summary)
    return _summary_out(db, record, summary)


@router.post("/records/{record_id}/guardian-summary/unapprove", response_model=GuardianSummaryOut)
def unapprove_guardian_summary(
    record_id: uuid.UUID, db: DbSession, user: ManagerUser
) -> GuardianSummaryOut:
    record = record_for_staff(db, user, record_id)
    summary = _require_summary(db, record.id)
    summary.status, summary.approved_by, summary.approved_at = "draft", None, None
    db.commit()
    db.refresh(summary)
    return _summary_out(db, record, summary)


# --- 방문 시작·종료 ---


def _session_out(s: VisitSession) -> VisitSessionOut:
    return VisitSessionOut(
        id=s.id,
        caregiver_id=s.caregiver_id,
        caregiver_name=s.caregiver.display_name,
        started_at=s.started_at,
        ended_at=s.ended_at,
    )


@router.get("/recipients/{recipient_id}/visits", response_model=list[VisitSessionOut])
def list_visits(recipient: StaffRecipient, db: DbSession) -> list[VisitSessionOut]:
    since = datetime.now(UTC) - timedelta(days=VISIT_DAYS)
    rows = db.scalars(
        select(VisitSession)
        .where(VisitSession.recipient_id == recipient.id, VisitSession.started_at >= since)
        .order_by(VisitSession.started_at.desc())
    )
    return [_session_out(s) for s in rows]


@router.post(
    "/recipients/{recipient_id}/visits/start",
    status_code=status.HTTP_201_CREATED,
    response_model=VisitSessionOut,
)
def start_visit(recipient: StaffRecipient, db: DbSession, user: CaregiverUser) -> VisitSessionOut:
    session = VisitSession(recipient_id=recipient.id, caregiver_id=user.id)
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "끝나지 않은 방문이 있습니다. 먼저 방문 종료를 눌러 주세요"
        ) from None
    db.refresh(session)
    return _session_out(session)


@router.post("/recipients/{recipient_id}/visits/end", response_model=VisitSessionOut)
def end_visit(recipient: StaffRecipient, db: DbSession, user: CaregiverUser) -> VisitSessionOut:
    session = db.scalar(
        select(VisitSession)
        .where(
            VisitSession.recipient_id == recipient.id,
            VisitSession.caregiver_id == user.id,
            VisitSession.ended_at.is_(None),
        )
        .with_for_update(of=VisitSession)  # 요양보호사를 joined로 같이 읽어서 잠글 표를 지정
    )
    if session is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "진행 중인 방문이 없습니다")
    session.ended_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return _session_out(session)


# --- 업무 메시지 ---


def _message_out(m: Message) -> MessageOut:
    return MessageOut.model_validate(
        {
            "id": m.id,
            "author_id": m.author_id,
            "author_name": m.author.display_name,
            "author_role": m.author.role,
            "body": m.body,
            "created_at": m.created_at,
        }
    )


@router.get("/recipients/{recipient_id}/messages", response_model=list[MessageOut])
def list_messages(recipient: StaffRecipient, db: DbSession) -> list[MessageOut]:
    """최근 메시지 (오래된 순으로 돌려준다)"""
    rows = db.scalars(
        select(Message)
        .where(Message.recipient_id == recipient.id)
        .order_by(Message.created_at.desc())
        .limit(MESSAGE_LIMIT)
    ).all()
    return [_message_out(m) for m in reversed(rows)]


@router.post(
    "/recipients/{recipient_id}/messages",
    status_code=status.HTTP_201_CREATED,
    response_model=MessageOut,
)
def post_message(
    body: MessageIn, recipient: StaffRecipient, db: DbSession, user: StaffUser
) -> MessageOut:
    message = Message(recipient_id=recipient.id, author_id=user.id, body=body.body)
    db.add(message)
    db.commit()
    db.refresh(message)
    return _message_out(message)
