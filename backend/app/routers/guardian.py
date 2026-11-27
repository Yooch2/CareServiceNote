"""보호자 화면. 직원용 응답을 거르지 않고 보여 줄 필드만 따로 만든다(허용 목록)."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.access import GuardianUser, has_consent
from app.deps import DbSession
from app.models import (
    Alert,
    FollowupCheck,
    GuardianLink,
    GuardianSummary,
    Recipient,
    RecordItem,
    VisitRecord,
    VisitSession,
)
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
    summaries = {
        s.record_id: s
        for s in db.scalars(
            select(GuardianSummary).where(
                GuardianSummary.record_id.in_([r.id for r in records]),
                GuardianSummary.status == "approved",
            )
        )
    }
    visits: list[GuardianVisitOut] = []
    for r in records:
        summary = _allowed_sentences(r, summaries.get(r.id), categories)
        items = [
            GuardianItemOut(category=i.category, content=i.content)  # type: ignore[arg-type]
            for i in r.items
            if i.category in categories
        ]
        checks = [_check_out(c) for c in r.followup_checks] if "followup" in categories else []
        if items or checks or summary:
            visits.append(
                GuardianVisitOut(
                    visited_on=r.visited_on, summary=summary, items=items, checks=checks
                )
            )

    since = datetime.now(UTC) - timedelta(days=GUARDIAN_DAYS)
    sessions = db.scalars(
        select(VisitSession)
        .where(VisitSession.recipient_id == link.recipient_id, VisitSession.started_at >= since)
        .order_by(VisitSession.started_at.desc())
    )
    notices = db.scalars(
        select(Alert)
        .where(
            Alert.recipient_id == link.recipient_id,
            Alert.shared_with.contains([user.id]),  # 담당자가 이 보호자를 고른 안내만
            Alert.shared_at >= since,
        )
        .order_by(Alert.shared_at.desc())
    )
    return GuardianHomeOut.model_validate(
        {
            "recipient_name": recipient.name,
            "categories": categories,
            # 요양보호사 이름 없이 시각만
            "sessions": [{"started_at": s.started_at, "ended_at": s.ended_at} for s in sessions],
            # 담당자가 보호자용으로 쓴 안내문만 (알림 근거·우려 원문은 보내지 않는다)
            "notices": [{"message": a.guardian_message, "shared_at": a.shared_at} for a in notices],
            "records": visits,
        }
    )


def _allowed_sentences(
    record: VisitRecord, summary: GuardianSummary | None, categories: list[str]
) -> list[str]:
    """승인된 요약 중 근거 항목이 모두 열람 범위 안에 있는 문장만"""
    if summary is None:
        return []
    category_of = {str(i.id): i.category for i in record.items}
    return [
        s["text"]
        for s in summary.sentences
        if s["item_ids"] and all(category_of.get(i) in categories for i in s["item_ids"])
    ]


def _check_out(check: FollowupCheck) -> GuardianCheckOut:
    item: RecordItem = check.followup_item
    return GuardianCheckOut(followup_content=item.content, result=check.result)
