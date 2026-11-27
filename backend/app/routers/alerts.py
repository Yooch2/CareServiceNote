"""변화 알림·긴급 우려·센터 인박스·기분·식사량 추이"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.access import (
    CaregiverUser,
    ManagerUser,
    StaffRecipient,
    require_health_consent,
)
from app.deps import DbSession
from app.models import Alert, GuardianLink, Recipient, User, VisitRecord
from app.schemas import AlertOut, ConcernIn, OrgAlertOut, ResolveIn, TrendPointOut

router = APIRouter(tags=["alerts"])

RESOLVED_LIMIT = 50


@router.get("/recipients/{recipient_id}/alerts", response_model=list[AlertOut])
def recipient_alerts(recipient: StaffRecipient, db: DbSession) -> list[Alert]:
    """이 수급자의 미처리 알림 (방문 전 확인 화면)"""
    return list(
        db.scalars(
            select(Alert)
            .where(Alert.recipient_id == recipient.id, Alert.status == "open")
            .order_by(Alert.created_at)
        )
    )


@router.post(
    "/recipients/{recipient_id}/concerns",
    status_code=status.HTTP_201_CREATED,
    response_model=AlertOut,
)
def submit_concern(
    body: ConcernIn, recipient: StaffRecipient, db: DbSession, user: CaregiverUser
) -> Alert:
    """요양보호사가 규칙과 관계없이 우려를 센터에 직접 올린다. 합치지 않는다.

    요양보호사에게 StaffRecipient는 지금 배정된 수급자만 통과시킨다.
    """
    require_health_consent(db, recipient.id)
    alert = Alert(
        recipient_id=recipient.id,
        kind="urgent",
        key=str(uuid.uuid4()),
        evidence=[],
        note=body.note,
        created_by=user.id,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.get("/recipients/{recipient_id}/trends", response_model=list[TrendPointOut])
def trends(
    recipient: StaffRecipient,
    db: DbSession,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
) -> list[TrendPointOut]:
    """확정 기록의 식사량·기분 (방문일 오름차순). 둘 다 없는 방문은 뺀다."""
    rows = db.scalars(
        select(VisitRecord)
        .where(
            VisitRecord.recipient_id == recipient.id,
            VisitRecord.status == "confirmed",
            VisitRecord.visited_on >= date.today() - timedelta(days=days),
        )
        .order_by(VisitRecord.visited_on, VisitRecord.created_at)
    ).all()
    return [
        TrendPointOut.model_validate(
            {
                "record_id": r.id,
                "visited_on": r.visited_on,
                "meal_level": r.meal_level,
                "mood": r.mood,
            }
        )
        for r in rows
        if r.meal_level is not None or r.mood is not None
    ]


@router.get("/org/alerts", response_model=list[OrgAlertOut])
def org_alerts(
    db: DbSession,
    user: ManagerUser,
    status_: Annotated[str, Query(alias="status", pattern="^(open|resolved)$")] = "open",
) -> list[OrgAlertOut]:
    """센터 인박스. 미처리는 오래된 순, 처리됨은 최근 순"""
    creator, resolver = aliased(User), aliased(User)
    stmt = (
        select(Alert, Recipient.name, creator.display_name, resolver.display_name)
        .join(Recipient, Alert.recipient_id == Recipient.id)
        .outerjoin(creator, Alert.created_by == creator.id)
        .outerjoin(resolver, Alert.resolved_by == resolver.id)
        .where(Recipient.org_id == user.org_id, Alert.status == status_)
    )
    if status_ == "open":
        stmt = stmt.order_by(Alert.created_at)
    else:
        stmt = stmt.order_by(Alert.resolved_at.desc()).limit(RESOLVED_LIMIT)
    rows = db.execute(stmt).all()
    guardians: dict[uuid.UUID, list[dict[str, object]]] = {}
    for link in db.scalars(
        select(GuardianLink).where(
            GuardianLink.recipient_id.in_({a.recipient_id for a, *_ in rows}),
            GuardianLink.active,
        )
    ):
        guardians.setdefault(link.recipient_id, []).append(
            {
                "guardian_id": link.guardian_id,
                "name": link.guardian.display_name,
                "categories": link.categories,
            }
        )
    return [
        OrgAlertOut.model_validate(
            {
                **AlertOut.model_validate(a).model_dump(),
                "recipient_name": name,
                "created_by_name": created_by,
                "resolved_by_name": resolved_by,
                "guardians": guardians.get(a.recipient_id, []),
            }
        )
        for a, name, created_by, resolved_by in rows
    ]


@router.post("/org/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: uuid.UUID, body: ResolveIn, db: DbSession, user: ManagerUser) -> Alert:
    alert = db.scalar(
        select(Alert)
        .join(Recipient, Alert.recipient_id == Recipient.id)
        .where(Alert.id == alert_id, Recipient.org_id == user.org_id)
        .with_for_update(of=Alert)
    )
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알림을 찾을 수 없습니다")
    if alert.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 처리한 알림입니다")
    alert.status, alert.resolution = "resolved", body.resolution
    alert.resolution_note = (body.note or "").strip() or None
    alert.resolved_by, alert.resolved_at = user.id, datetime.now(UTC)
    message = (body.guardian_message or "").strip()
    if message:
        targets = set(body.guardian_ids)
        allowed = set(
            db.scalars(
                select(GuardianLink.guardian_id).where(
                    GuardianLink.recipient_id == alert.recipient_id, GuardianLink.active
                )
            )
        )
        if not targets or not targets <= allowed:
            db.rollback()
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "안내를 받을 보호자를 골라 주세요"
            )
        alert.guardian_message, alert.shared_at = message, alert.resolved_at
        alert.shared_with = sorted(targets)
    db.commit()
    db.refresh(alert)
    return alert
