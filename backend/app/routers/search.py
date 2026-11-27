from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select

from app.access import StaffRecipient, StaffUser
from app.audit import audit
from app.deps import DbSession
from app.models import FollowupCheck, RecordItem, VisitRecord
from app.schemas import Category, SearchHitOut

router = APIRouter(prefix="/recipients", tags=["search"])

MAX_HITS = 50
SNIPPET_WIDTH = 40


def like_pattern(q: str) -> str:
    """ILIKE 패턴. 사용자가 넣은 %, _ 는 글자 그대로 찾도록 이스케이프한다."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def snippet(text: str, q: str, width: int = SNIPPET_WIDTH) -> str:
    """전사문은 일치한 곳 앞뒤만 잘라서 보낸다."""
    pos = text.lower().find(q.lower())
    if pos < 0:
        return text[: width * 2]
    start, end = max(0, pos - width), min(len(text), pos + len(q) + width)
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


@router.get("/{recipient_id}/search", response_model=list[SearchHitOut])
def search(
    recipient: StaffRecipient,
    db: DbSession,
    user: StaffUser,
    q: Annotated[str, Query(max_length=100)],
    category: Category | None = None,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
) -> list[SearchHitOut]:
    """확정된 기록 안에서 항목 내용·근거, 확인 결과, 전사문을 찾는다 (수급자 한 명 범위)."""
    recipient_id = recipient.id
    q = q.strip()
    if not 2 <= len(q) <= 50:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "검색어는 2~50자로 입력해 주세요"
        )
    audit(db, user, "search", recipient_id)  # 검색어는 남기지 않는다
    pattern = like_pattern(q)
    scope = [VisitRecord.recipient_id == recipient_id, VisitRecord.status == "confirmed"]
    if days is not None:
        scope.append(VisitRecord.visited_on >= date.today() - timedelta(days=days))

    hits: list[SearchHitOut] = []
    item_stmt = (
        select(RecordItem, VisitRecord.visited_on)
        .join(VisitRecord, RecordItem.record_id == VisitRecord.id)
        .where(
            *scope,
            or_(
                RecordItem.content.ilike(pattern, escape="\\"),
                RecordItem.evidence.ilike(pattern, escape="\\"),
            ),
        )
    )
    if category is not None:
        item_stmt = item_stmt.where(RecordItem.category == category)
    for item, visited_on in db.execute(item_stmt.limit(MAX_HITS)).all():
        hits.append(
            SearchHitOut.model_validate(
                {
                    "record_id": item.record_id,
                    "visited_on": visited_on,
                    "kind": "item",
                    "category": item.category,
                    "text": item.content,
                    "item_id": item.id,
                }
            )
        )

    # 분류를 고르면 항목만 찾는다 (확인 결과·전사문에는 분류가 없음)
    if category is None:
        checks = db.execute(
            select(FollowupCheck, RecordItem.content, VisitRecord.visited_on)
            .join(VisitRecord, FollowupCheck.record_id == VisitRecord.id)
            .join(RecordItem, FollowupCheck.followup_item_id == RecordItem.id)
            .where(*scope, FollowupCheck.result.ilike(pattern, escape="\\"))
            .limit(MAX_HITS)
        ).all()
        for check, content, visited_on in checks:
            hits.append(
                SearchHitOut(
                    record_id=check.record_id,
                    visited_on=visited_on,
                    kind="check",
                    category=None,
                    text=f"{content} → {check.result}",
                    item_id=check.followup_item_id,
                )
            )
        records = db.execute(
            select(VisitRecord.id, VisitRecord.visited_on, VisitRecord.transcript)
            .where(*scope, VisitRecord.transcript.ilike(pattern, escape="\\"))
            .limit(MAX_HITS)
        ).all()
        for record_id, visited_on, transcript in records:
            hits.append(
                SearchHitOut(
                    record_id=record_id,
                    visited_on=visited_on,
                    kind="transcript",
                    category=None,
                    text=snippet(transcript or "", q),
                    item_id=None,
                )
            )

    hits.sort(key=lambda h: h.visited_on, reverse=True)
    return hits[:MAX_HITS]
