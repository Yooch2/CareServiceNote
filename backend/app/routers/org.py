"""기관 담당자의 센터 관리: 구성원, 초대 코드, 보호자 연결, 확인 대기 기록"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.access import ManagerUser, recipient_for_staff
from app.deps import DbSession
from app.invites import hash_code, new_code
from app.models import GuardianLink, Invite, Recipient, User, VisitRecord
from app.schemas import (
    GuardianLinkPatch,
    InviteCreatedOut,
    InviteIn,
    InviteOut,
    MemberOut,
    MemberPatch,
    ReviewQueueOut,
)

router = APIRouter(prefix="/org", tags=["org"])

INVITE_TTL = timedelta(days=7)


@router.get("/members", response_model=list[MemberOut])
def list_members(db: DbSession, user: ManagerUser) -> list[MemberOut]:
    rows = db.execute(
        select(User, Recipient.name)
        .outerjoin(GuardianLink, GuardianLink.guardian_id == User.id)
        .outerjoin(Recipient, GuardianLink.recipient_id == Recipient.id)
        .where(User.org_id == user.org_id)
        .order_by(User.role, User.created_at)
    ).all()
    return [
        MemberOut.model_validate(
            {
                "id": m.id,
                "login_id": m.login_id,
                "display_name": m.display_name,
                "role": m.role,
                "active": m.active,
                "recipient_name": recipient_name,
            }
        )
        for m, recipient_name in rows
    ]


@router.patch("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_member(user_id: uuid.UUID, body: MemberPatch, db: DbSession, user: ManagerUser) -> None:
    member = db.get(User, user_id)
    if member is None or member.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "구성원을 찾을 수 없습니다")
    if member.id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "내 계정은 비활성화할 수 없습니다")
    member.active = body.active
    db.commit()


@router.post("/invites", status_code=status.HTTP_201_CREATED, response_model=InviteCreatedOut)
def create_invite(body: InviteIn, db: DbSession, user: ManagerUser) -> InviteCreatedOut:
    if body.recipient_id is not None:
        recipient_for_staff(db, user, body.recipient_id)  # 같은 센터 수급자인지
    code = new_code()
    invite = Invite(
        org_id=user.org_id,
        role=body.role,
        recipient_id=body.recipient_id,
        categories=body.categories,
        code_hash=hash_code(code),
        expires_at=datetime.now(UTC) + INVITE_TTL,
        created_by=user.id,
    )
    db.add(invite)
    db.commit()
    return InviteCreatedOut(id=invite.id, code=code, expires_at=invite.expires_at)


@router.get("/invites", response_model=list[InviteOut])
def list_invites(db: DbSession, user: ManagerUser) -> list[InviteOut]:
    rows = db.execute(
        select(Invite, Recipient.name)
        .outerjoin(Recipient, Invite.recipient_id == Recipient.id)
        .where(
            Invite.org_id == user.org_id,
            Invite.used_at.is_(None),
            Invite.expires_at > datetime.now(UTC),
        )
        .order_by(Invite.created_at.desc())
    ).all()
    return [
        InviteOut.model_validate(
            {
                "id": i.id,
                "role": i.role,
                "recipient_name": name,
                "categories": i.categories,
                "expires_at": i.expires_at,
            }
        )
        for i, name in rows
    ]


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_invite(invite_id: uuid.UUID, db: DbSession, user: ManagerUser) -> None:
    invite = db.get(Invite, invite_id)
    if invite is None or invite.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "초대를 찾을 수 없습니다")
    if invite.used_at is None:
        db.delete(invite)
        db.commit()


@router.patch("/guardian-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_guardian_link(
    link_id: uuid.UUID, body: GuardianLinkPatch, db: DbSession, user: ManagerUser
) -> None:
    link = db.get(GuardianLink, link_id)
    if link is None or link.guardian.org_id != user.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보호자 연결을 찾을 수 없습니다")
    if body.categories is not None:
        link.categories = sorted(set(body.categories))
    if body.active is not None:
        link.active = body.active
    db.commit()


@router.get("/reviews", response_model=list[ReviewQueueOut])
def review_queue(db: DbSession, user: ManagerUser) -> list[ReviewQueueOut]:
    """센터 확인 서명을 기다리는 확정 기록 (오래된 순)"""
    caregiver = aliased(User)
    rows = db.execute(
        select(VisitRecord, Recipient.name, caregiver.display_name)
        .join(Recipient, VisitRecord.recipient_id == Recipient.id)
        .join(caregiver, VisitRecord.caregiver_id == caregiver.id)
        .where(
            Recipient.org_id == user.org_id,
            VisitRecord.status == "confirmed",
            VisitRecord.reviewed_at.is_(None),
        )
        .order_by(VisitRecord.confirmed_at)
    ).all()
    return [
        ReviewQueueOut.model_validate(
            {
                "record_id": r.id,
                "recipient_id": r.recipient_id,
                "recipient_name": name,
                "visited_on": r.visited_on,
                "caregiver_name": caregiver_name,
                "confirmed_at": r.confirmed_at,
            }
        )
        for r, name, caregiver_name in rows
    ]
