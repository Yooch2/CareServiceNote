"""보호자 화면. 직원용 응답을 거르지 않고 보여 줄 필드만 따로 만든다(허용 목록)."""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.access import GuardianUser, has_consent
from app.deps import DbSession
from app.models import FollowupCheck, GuardianLink, Recipient, RecordItem, VisitRecord
from app.schemas import GuardianCheckOut, GuardianHomeOut, GuardianItemOut, GuardianVisitOut

router = APIRouter(prefix="/guardian", tags=["guardian"])

GUARDIAN_DAYS = 30


@router.get("/home", response_model=GuardianHomeOut)
def guardian_home(db: DbSession, user: GuardianUser) -> GuardianHomeOut:
    link = db.scalar(select(GuardianLink).where(GuardianLink.guardian_id == user.id))
    if link is None or not link.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "보호자 연결이 해제되었습니다")
    if not has_consent(db, link.recipient_id, "guardian_share"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "수급자의 공유 동의가 없어 기록을 볼 수 없습니다"
        )
    recipient = db.get(Recipient, link.recipient_id)
    assert recipient is not None
    categories = link.categories

    records = db.scalars(
        select(VisitRecord)
        .where(
            VisitRecord.recipient_id == link.recipient_id,
            VisitRecord.status == "confirmed",
            VisitRecord.visited_on >= date.today() - timedelta(days=GUARDIAN_DAYS),
        )
        .order_by(VisitRecord.visited_on.desc(), VisitRecord.created_at.desc())
    ).all()
    visits: list[GuardianVisitOut] = []
    for r in records:
        items = [
            GuardianItemOut(category=i.category, content=i.content)  # type: ignore[arg-type]
            for i in r.items
            if i.category in categories
        ]
        checks = [_check_out(c) for c in r.followup_checks] if "followup" in categories else []
        if items or checks:
            visits.append(GuardianVisitOut(visited_on=r.visited_on, items=items, checks=checks))
    return GuardianHomeOut.model_validate(
        {"recipient_name": recipient.name, "categories": categories, "records": visits}
    )


def _check_out(check: FollowupCheck) -> GuardianCheckOut:
    item: RecordItem = check.followup_item
    return GuardianCheckOut(followup_content=item.content, result=check.result)
