from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AiUsage, User

_LOCK_KEY = 7_301_002  # 요약 한도 확인용 advisory lock 번호


def reserve_ai_call(db: Session, user: User, kind: str) -> None:
    """한도를 확인하고 AI를 부르기 전에 사용 기록을 남긴다 (실패한 시도도 센다).

    인계 요약과 보호자 요약은 같은 하루 한도를 같이 쓴다(종류만 다르게 남긴다).
    확인과 기록을 잠금으로 묶어 동시 요청으로 한도를 넘지 못하게 한다. 커밋하면 잠금이 풀린다.
    """
    db.execute(select(func.pg_advisory_xact_lock(_LOCK_KEY)))
    base = (
        select(func.count())
        .select_from(AiUsage)
        .where(AiUsage.created_at > func.now() - timedelta(days=1))
    )
    mine = db.scalar(base.where(AiUsage.user_id == user.id)) or 0
    total = db.scalar(base) or 0
    if mine >= settings.daily_summaries_per_user or total >= settings.daily_summaries_total:
        db.rollback()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "오늘 만들 수 있는 요약 수를 넘었습니다"
        )
    db.add(AiUsage(user_id=user.id, kind=kind))
    db.commit()
