import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.errors import AIError, TransientAIError
from app.ai.factory import build_llm
from app.ai.summary import clean_summary, summarize
from app.ai.types import StructuredLLM
from app.config import settings
from app.deps import CurrentUser, DbSession
from app.followups import open_followups
from app.models import FollowupCheck, HandoverSummary, RecordItem, VisitRecord
from app.routers.recipients import get_recipient_or_404
from app.schemas import (
    CompletionOut,
    Days,
    HandoverOut,
    OpenFollowupOut,
    RecentCheckOut,
    RiskItemOut,
    SummaryOutApi,
)

router = APIRouter(prefix="/recipients", tags=["handover"])


def period_days(days: Annotated[int, Query()] = 14) -> int:
    """조회 기간은 7·14·30일만 (쿼리 문자열이라 Literal 대신 직접 확인)"""
    if days not in get_args(Days):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "기간은 7, 14, 30일 중 하나입니다"
        )
    return days


DaysQuery = Annotated[int, Depends(period_days)]
MAX_SUMMARY_LINES = 60
_CATEGORY_KO = {"remark": "말씀", "observation": "관찰", "followup": "다음 확인"}


def get_llm() -> StructuredLLM:
    try:
        return build_llm()
    except AIError:
        # 예: Gemini 키가 없음. 규칙 묶음은 그대로 쓸 수 있으므로 요약만 실패로 알린다.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, _SUMMARY_FAILED) from None


_SUMMARY_FAILED = "AI 요약을 만들지 못했습니다"


def _since(days: int) -> date:
    # ponytail: 서버 날짜 기준. 방문일은 기기 날짜라 자정 무렵 하루 차이가 날 수 있다.
    return date.today() - timedelta(days=days)


def _confirmed_in_period(recipient_id: uuid.UUID, days: int) -> Any:
    return (
        VisitRecord.recipient_id == recipient_id,
        VisitRecord.status == "confirmed",
        VisitRecord.visited_on >= _since(days),
    )


@router.get("/{recipient_id}/handover", response_model=HandoverOut)
def get_handover(
    recipient_id: uuid.UUID, db: DbSession, _: CurrentUser, days: DaysQuery
) -> HandoverOut:
    """방문 전 확인 묶음.

    남은 확인 사항은 기간과 관계없이 전부, 위험 항목·확인 결과·완료율은 기간 안, 저장된 AI 요약.
    """
    get_recipient_or_404(db, recipient_id)
    period = _confirmed_in_period(recipient_id, days)

    last_visit_on = db.scalar(
        select(func.max(VisitRecord.visited_on)).where(
            VisitRecord.recipient_id == recipient_id, VisitRecord.status == "confirmed"
        )
    )
    risk_rows = db.execute(
        select(RecordItem, VisitRecord.visited_on)
        .join(VisitRecord, RecordItem.record_id == VisitRecord.id)
        .where(*period, RecordItem.risk_tag.is_not(None))
        .order_by(VisitRecord.visited_on.desc(), RecordItem.position)
    ).all()
    check_rows = db.execute(
        select(FollowupCheck, RecordItem.content, VisitRecord.visited_on)
        .join(VisitRecord, FollowupCheck.record_id == VisitRecord.id)
        .join(RecordItem, FollowupCheck.followup_item_id == RecordItem.id)
        .where(*period)
        .order_by(VisitRecord.visited_on.desc(), FollowupCheck.created_at.desc())
    ).all()
    due_rows = db.execute(
        select(RecordItem.id, FollowupCheck.id)
        .join(VisitRecord, RecordItem.record_id == VisitRecord.id)
        .outerjoin(FollowupCheck, FollowupCheck.followup_item_id == RecordItem.id)
        .where(*period, RecordItem.category == "followup")
    ).all()

    return HandoverOut(
        days=days,
        last_visit_on=last_visit_on,
        open_followups=[
            OpenFollowupOut(
                item_id=o.item_id,
                content=o.content,
                evidence=o.evidence,
                record_id=o.record_id,
                visited_on=o.visited_on,
            )
            for o in open_followups(db, recipient_id)
        ],
        risk_items=[
            RiskItemOut.model_validate(
                {
                    "item_id": item.id,
                    "category": item.category,
                    "content": item.content,
                    "risk_tag": item.risk_tag,
                    "record_id": item.record_id,
                    "visited_on": visited_on,
                }
            )
            for item, visited_on in risk_rows
        ],
        recent_checks=[
            RecentCheckOut.model_validate(
                {
                    "followup_item_id": check.followup_item_id,
                    "followup_content": content,
                    "result": check.result,
                    "origin": check.origin,
                    "record_id": check.record_id,
                    "visited_on": visited_on,
                }
            )
            for check, content, visited_on in check_rows
        ],
        completion=CompletionOut(
            due=len(due_rows), checked=sum(1 for _, check_id in due_rows if check_id)
        ),
        summary=_latest_summary(db, recipient_id, days),
    )


def _latest_summary(db: Session, recipient_id: uuid.UUID, days: int) -> SummaryOutApi | None:
    summary = db.scalar(
        select(HandoverSummary)
        .where(HandoverSummary.recipient_id == recipient_id, HandoverSummary.days == days)
        .order_by(HandoverSummary.created_at.desc())
        .limit(1)
    )
    if summary is None:
        return None
    return _summary_out(db, summary)


def _summary_out(db: Session, summary: HandoverSummary) -> SummaryOutApi:
    newer = select(VisitRecord.id).where(*_confirmed_in_period(summary.recipient_id, summary.days))
    if summary.covered_until is not None:
        newer = newer.where(VisitRecord.confirmed_at > summary.covered_until)
    stale = db.scalar(newer.limit(1)) is not None
    return SummaryOutApi.model_validate(
        {"sentences": summary.sentences, "created_at": summary.created_at, "stale": stale}
    )


@dataclass(frozen=True)
class _Ref:
    item_id: uuid.UUID
    record_id: uuid.UUID
    visited_on: date


def _summary_lines(
    db: Session, recipient_id: uuid.UUID, days: int
) -> tuple[list[str], dict[str, _Ref], datetime | None]:
    """요약에 넣을 줄(I1, I2 ...)과 참조 번호 → 근거 항목. 이름·UUID는 넣지 않는다."""
    period = _confirmed_in_period(recipient_id, days)
    items = db.execute(
        select(RecordItem, VisitRecord.visited_on)
        .join(VisitRecord, RecordItem.record_id == VisitRecord.id)
        .where(*period)
        .order_by(VisitRecord.visited_on.desc(), VisitRecord.created_at.desc(), RecordItem.position)
        .limit(MAX_SUMMARY_LINES)
    ).all()
    checks = db.execute(
        select(FollowupCheck, RecordItem.content, VisitRecord.visited_on)
        .join(VisitRecord, FollowupCheck.record_id == VisitRecord.id)
        .join(RecordItem, FollowupCheck.followup_item_id == RecordItem.id)
        .where(*period)
        .order_by(VisitRecord.visited_on.desc())
        .limit(MAX_SUMMARY_LINES)
    ).all()
    covered_until = db.scalar(select(func.max(VisitRecord.confirmed_at)).where(*period))

    lines: list[str] = []
    refs: dict[str, _Ref] = {}
    for item, visited_on in items:
        ref = f"I{len(lines) + 1}"
        lines.append(f"{ref}. [{visited_on}] [{_CATEGORY_KO[item.category]}] {item.content}")
        refs[ref] = _Ref(item.id, item.record_id, visited_on)
    for check, content, visited_on in checks:
        if len(lines) >= MAX_SUMMARY_LINES:
            break
        ref = f"I{len(lines) + 1}"
        lines.append(f"{ref}. [{visited_on}] [확인 결과] {content} → {check.result}")
        refs[ref] = _Ref(check.followup_item_id, check.record_id, visited_on)
    return lines, refs, covered_until


@router.post("/{recipient_id}/handover/summary", response_model=SummaryOutApi)
def create_summary(
    recipient_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    llm: Annotated[StructuredLLM, Depends(get_llm)],
    days: DaysQuery,
) -> SummaryOutApi:
    """기간 내 확정 항목으로 AI 인계 요약을 만든다. 문장마다 근거 항목이 있어야 남긴다."""
    get_recipient_or_404(db, recipient_id)
    made_today = db.scalar(
        select(func.count())
        .select_from(HandoverSummary)
        .where(
            HandoverSummary.created_by == user.id,
            HandoverSummary.created_at > func.now() - timedelta(days=1),
        )
    )
    if (made_today or 0) >= settings.daily_summaries_per_user:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "오늘 만들 수 있는 요약 수를 넘었습니다"
        )

    lines, refs, covered_until = _summary_lines(db, recipient_id, days)
    if not lines:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "요약할 확정 기록이 없습니다")
    try:
        cleaned = clean_summary(summarize(llm, lines), refs)
    except TransientAIError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "AI 요약을 잠시 만들 수 없습니다"
        ) from None
    except AIError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, _SUMMARY_FAILED) from None
    if not cleaned:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, _SUMMARY_FAILED)

    summary = HandoverSummary(
        recipient_id=recipient_id,
        days=days,
        sentences=[
            {
                "text": text,
                "items": [
                    {
                        "item_id": str(r.item_id),
                        "record_id": str(r.record_id),
                        "visited_on": r.visited_on.isoformat(),
                    }
                    for r in targets
                ],
            }
            for text, targets in cleaned
        ],
        covered_until=covered_until,
        created_by=user.id,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return _summary_out(db, summary)
