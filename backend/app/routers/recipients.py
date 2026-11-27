import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.access import (
    ManagedRecipient,
    ManagerUser,
    StaffRecipient,
    StaffUser,
    visible_recipients,
)
from app.deps import DbSession
from app.models import Assignment, Consent, GuardianLink, Recipient, User, VisitRecord
from app.schemas import (
    AssignmentIn,
    AssignmentOut,
    ConsentIn,
    ConsentOut,
    GuardianLinkOut,
    RecipientAdminOut,
    RecipientIn,
    RecipientOut,
    RecordSummaryOut,
)

router = APIRouter(prefix="/recipients", tags=["recipients"])


@router.get("", response_model=list[RecipientOut])
def list_recipients(db: DbSession, user: StaffUser) -> Sequence[Recipient]:
    """기관 담당자는 센터 전체, 요양보호사는 지금 배정된 수급자"""
    return db.scalars(visible_recipients(user).order_by(Recipient.created_at, Recipient.id)).all()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RecipientOut)
def create_recipient(body: RecipientIn, db: DbSession, user: ManagerUser) -> Recipient:
    recipient = Recipient(name=body.name, org_id=user.org_id)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)  # server_default인 created_at 읽어오기
    return recipient


@router.get("/{recipient_id}", response_model=RecipientOut)
def get_recipient(recipient: StaffRecipient) -> Recipient:
    return recipient


@router.get("/{recipient_id}/records", response_model=list[RecordSummaryOut])
def list_records(
    recipient: StaffRecipient, db: DbSession, user: StaffUser
) -> list[RecordSummaryOut]:
    """확정된 기록은 모두, 확정 전 기록은 내가 쓴 것만 보여 준다."""
    rows = db.scalars(
        select(VisitRecord)
        .where(
            VisitRecord.recipient_id == recipient.id,
            or_(VisitRecord.status == "confirmed", VisitRecord.caregiver_id == user.id),
        )
        .order_by(VisitRecord.visited_on.desc(), VisitRecord.created_at.desc())
    ).all()
    return [
        RecordSummaryOut(
            id=r.id,
            visited_on=r.visited_on,
            status=r.status,
            is_mine=r.caregiver_id == user.id,
            created_at=r.created_at,
        )
        for r in rows
    ]


# --- 기관 담당자: 담당 배정 · 동의 · 보호자 ---


@router.get("/{recipient_id}/admin", response_model=RecipientAdminOut)
def get_admin(recipient: ManagedRecipient, db: DbSession, _: ManagerUser) -> RecipientAdminOut:
    assignments = db.scalars(
        select(Assignment)
        .where(Assignment.recipient_id == recipient.id)
        .order_by(Assignment.ended_at.desc().nulls_first(), Assignment.started_at.desc())
    ).all()
    pending = dict(
        db.execute(
            select(VisitRecord.caregiver_id, func.count())
            .where(VisitRecord.recipient_id == recipient.id, VisitRecord.status != "confirmed")
            .group_by(VisitRecord.caregiver_id)
        ).all()
    )
    consents = db.scalars(
        select(Consent)
        .where(Consent.recipient_id == recipient.id)
        .order_by(Consent.created_at.desc())
    ).all()
    links = db.scalars(
        select(GuardianLink)
        .where(GuardianLink.recipient_id == recipient.id)
        .order_by(GuardianLink.created_at)
    ).all()
    return RecipientAdminOut(
        assignments=[
            AssignmentOut(
                id=a.id,
                caregiver_id=a.caregiver_id,
                caregiver_name=a.caregiver.display_name,
                started_at=a.started_at,
                ended_at=a.ended_at,
                pending_records=pending.get(a.caregiver_id, 0) if a.ended_at is None else 0,
            )
            for a in assignments
        ],
        consents=[ConsentOut.model_validate(c) for c in consents],
        guardians=[
            GuardianLinkOut.model_validate(
                {
                    "id": g.id,
                    "guardian_id": g.guardian_id,
                    "guardian_name": g.guardian.display_name,
                    "categories": g.categories,
                    "active": g.active,
                    "guardian_active": g.guardian.active,
                }
            )
            for g in links
        ],
    )


@router.post("/{recipient_id}/assignments", status_code=status.HTTP_201_CREATED)
def add_assignment(
    body: AssignmentIn, recipient: ManagedRecipient, db: DbSession, user: ManagerUser
) -> dict[str, uuid.UUID]:
    caregiver = db.get(User, body.caregiver_id)
    if (
        caregiver is None
        or caregiver.org_id != user.org_id
        or caregiver.role != "caregiver"
        or not caregiver.active
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "같은 센터의 요양보호사만 배정할 수 있습니다"
        )
    assignment = Assignment(
        recipient_id=recipient.id, caregiver_id=caregiver.id, created_by=user.id
    )
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 배정된 요양보호사입니다") from None
    return {"id": assignment.id}


@router.delete(
    "/{recipient_id}/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT
)
def end_assignment(
    assignment_id: uuid.UUID, recipient: ManagedRecipient, db: DbSession, _: ManagerUser
) -> None:
    assignment = db.get(Assignment, assignment_id)
    if assignment is None or assignment.recipient_id != recipient.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "배정을 찾을 수 없습니다")
    if assignment.ended_at is None:
        assignment.ended_at = datetime.now(UTC)
        db.commit()


@router.post(
    "/{recipient_id}/consents", status_code=status.HTTP_201_CREATED, response_model=ConsentOut
)
def record_consent(
    body: ConsentIn, recipient: ManagedRecipient, db: DbSession, user: ManagerUser
) -> Consent:
    # ponytail: 서버 날짜 기준. 자정 무렵 기기 날짜와 하루 차이가 날 수 있다.
    if body.granted_on > date.today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "동의 받은 날은 미래일 수 없습니다"
        )
    consent = Consent(
        recipient_id=recipient.id, kind=body.kind, granted_on=body.granted_on, recorded_by=user.id
    )
    db.add(consent)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 유효한 동의가 있습니다") from None
    db.refresh(consent)
    return consent


@router.post("/{recipient_id}/consents/{consent_id}/withdraw", response_model=ConsentOut)
def withdraw_consent(
    consent_id: uuid.UUID, recipient: ManagedRecipient, db: DbSession, user: ManagerUser
) -> Consent:
    consent = db.get(Consent, consent_id)
    if consent is None or consent.recipient_id != recipient.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "동의 기록을 찾을 수 없습니다")
    if consent.withdrawn_at is None:
        consent.withdrawn_at, consent.withdrawn_by = datetime.now(UTC), user.id
        db.commit()
    return consent
