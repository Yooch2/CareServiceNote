"""누가 어떤 수급자·기록을 볼 수 있는지 정하는 곳. 수급자·기록 엔드포인트는 모두 여기를 거친다.

- 기관 담당자: 같은 센터의 수급자 전부, 확정 기록만
- 요양보호사: 지금 배정된 수급자, 확정 기록 + 내가 쓴 확정 전 기록
- 보호자: 이 모듈의 직원용 함수는 쓰지 못한다 (보호자 API만)

볼 수 없는 수급자·기록은 존재 여부를 숨기려고 404, 역할이 맞지 않는 요청은 403.
"""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import ColumnElement, Select, exists, false, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models import Assignment, Consent, Recipient, User, VisitRecord

RECIPIENT_NOT_FOUND = "수급자를 찾을 수 없습니다"
RECORD_NOT_FOUND = "기록을 찾을 수 없습니다"
NO_HEALTH_CONSENT = "건강정보 처리 동의가 없어 기록·요약할 수 없습니다"


def require_role(*roles: str) -> Callable[[User], User]:
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "이 계정으로는 쓸 수 없는 기능입니다")
        return user

    return check


StaffUser = Annotated[User, Depends(require_role("manager", "caregiver"))]
ManagerUser = Annotated[User, Depends(require_role("manager"))]
CaregiverUser = Annotated[User, Depends(require_role("caregiver"))]
GuardianUser = Annotated[User, Depends(require_role("guardian"))]


def _assigned(caregiver_id: uuid.UUID, recipient_id: Any) -> ColumnElement[bool]:
    return exists().where(
        Assignment.recipient_id == recipient_id,
        Assignment.caregiver_id == caregiver_id,
        Assignment.ended_at.is_(None),
    )


def is_assigned(db: Session, caregiver_id: uuid.UUID, recipient_id: uuid.UUID) -> bool:
    return bool(db.scalar(select(_assigned(caregiver_id, recipient_id))))


def visible_recipients(user: User) -> Select[Recipient]:
    """직원이 볼 수 있는 수급자 (보호자는 호출하지 않는다)"""
    stmt = select(Recipient).where(Recipient.org_id == user.org_id)
    if user.role == "caregiver":
        stmt = stmt.where(_assigned(user.id, Recipient.id))
    elif user.role != "manager":
        stmt = stmt.where(false())
    return stmt


def recipient_for_staff(db: Session, user: User, recipient_id: uuid.UUID) -> Recipient:
    recipient = db.scalar(visible_recipients(user).where(Recipient.id == recipient_id))
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, RECIPIENT_NOT_FOUND)
    return recipient


def staff_recipient(recipient_id: uuid.UUID, db: DbSession, user: StaffUser) -> Recipient:
    return recipient_for_staff(db, user, recipient_id)


def managed_recipient(recipient_id: uuid.UUID, db: DbSession, user: ManagerUser) -> Recipient:
    return recipient_for_staff(db, user, recipient_id)


StaffRecipient = Annotated[Recipient, Depends(staff_recipient)]
ManagedRecipient = Annotated[Recipient, Depends(managed_recipient)]


def has_consent(db: Session, recipient_id: uuid.UUID, kind: str) -> bool:
    return bool(
        db.scalar(
            select(
                exists().where(
                    Consent.recipient_id == recipient_id,
                    Consent.kind == kind,
                    Consent.withdrawn_at.is_(None),
                )
            )
        )
    )


def require_health_consent(db: Session, recipient_id: uuid.UUID) -> None:
    if not has_consent(db, recipient_id, "health_record"):
        raise HTTPException(status.HTTP_409_CONFLICT, NO_HEALTH_CONSENT)


def record_for_staff(
    db: Session, user: User, record_id: uuid.UUID, *, own: bool = False, for_update: bool = False
) -> VisitRecord:
    """수급자를 볼 수 있어야 하고, 확정 전 기록(또는 own=True)은 작성자 본인만."""
    stmt = select(VisitRecord).where(VisitRecord.id == record_id)
    if for_update:
        stmt = stmt.with_for_update()
    record = db.scalar(stmt)
    if record is None or user.role not in ("manager", "caregiver"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, RECORD_NOT_FOUND)
    if (own or record.status != "confirmed") and record.caregiver_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, RECORD_NOT_FOUND)
    visible = db.scalar(
        select(visible_recipients(user).where(Recipient.id == record.recipient_id).exists())
    )
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, RECORD_NOT_FOUND)
    return record
