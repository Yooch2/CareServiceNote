import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FollowupCheck, RecordItem, VisitRecord


@dataclass(frozen=True)
class OpenItem:
    item_id: uuid.UUID
    content: str
    evidence: str | None
    record_id: uuid.UUID
    visited_on: date


def open_followups(
    db: Session, recipient_id: uuid.UUID, limit: int | None = None
) -> list[OpenItem]:
    """수급자의 확정 기록에 있는 '다음 확인' 항목 중 아직 확인 결과가 없는 것 (최근 방문 순).

    작성자와 관계없이 수급자 기준이다. 담당자가 바뀌어도 이어서 확인하게 하려는 것.
    """
    stmt = (
        select(RecordItem, VisitRecord.visited_on)
        .join(VisitRecord, RecordItem.record_id == VisitRecord.id)
        .outerjoin(FollowupCheck, FollowupCheck.followup_item_id == RecordItem.id)
        .where(
            VisitRecord.recipient_id == recipient_id,
            VisitRecord.status == "confirmed",
            RecordItem.category == "followup",
            FollowupCheck.id.is_(None),
        )
        .order_by(VisitRecord.visited_on.desc(), VisitRecord.created_at.desc(), RecordItem.position)
        .limit(limit)
    )
    return [
        OpenItem(item.id, item.content, item.evidence, item.record_id, visited_on)
        for item, visited_on in db.execute(stmt).all()
    ]
