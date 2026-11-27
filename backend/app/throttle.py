"""로그인·초대 코드 시도 횟수 제한 (무작위 대입 방지).

시도를 확인하기 **전에** 실패 한 번으로 미리 기록하고(잠금 안에서 개수 확인 + 기록 + 커밋),
성공하면 그 기록을 지운다. 확인과 기록이 한 잠금 안에 있어 동시 요청으로 한도를 넘지 못한다.

- 로그인: (아이디 + 클라이언트 IP)별 15분 5번, IP별 15분 30번.
  다른 네트워크에서 남의 아이디로 실패를 쌓아도 그 사람은 막히지 않는다.
  없는 아이디도 같은 방식으로 세서 막히는지로 아이디 존재를 알 수 없다.
- 초대 코드: IP별 한 시간 10번. 다른 사람의 실패로 올바른 코드가 막히지 않는다.

키는 해시만 저장한다 (아이디·IP 원문을 남기지 않음).
"""

import hashlib
import uuid
from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthFailure

_LOCK = 7_301_004  # advisory lock 번호 (키별 두 번째 값)


def client_ip(request: Request) -> str:
    """운영(TRUST_PROXY)에서는 Caddy가 넣은 X-Forwarded-For를, 아니면 직접 연결한 주소를 쓴다.

    API는 Caddy를 거쳐서만 닿게 배포한다(포트를 밖으로 열지 않음). Caddy는 신뢰하지 않는
    클라이언트가 보낸 X-Forwarded-For를 실제 접속 주소로 덮어쓴다.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if settings.trust_proxy and forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _reserve(
    db: Session, rules: list[tuple[str, str, int, timedelta]], message: str
) -> list[uuid.UUID]:
    """(종류, 키, 한도, 기간) 규칙을 모두 확인하고, 통과하면 실패 한 번씩 미리 기록한다."""
    for kind, key, _, _ in sorted(rules):  # 같은 순서로 잠가 교착을 피한다
        db.execute(select(func.pg_advisory_xact_lock(_LOCK, func.hashtext(f"{kind}:{key}"))))
    for kind, key, limit, window in rules:
        count = db.scalar(
            select(func.count())
            .select_from(AuthFailure)
            .where(
                AuthFailure.kind == kind,
                AuthFailure.key == key,
                AuthFailure.created_at > func.now() - window,
            )
        )
        if (count or 0) >= limit:
            db.rollback()
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message)
    rows = [AuthFailure(kind=kind, key=key) for kind, key, _, _ in rules]
    db.add_all(rows)
    db.commit()  # 잠금이 풀리고, 이 시도는 실패로 세어진 상태
    return [r.id for r in rows]


def release(db: Session, ids: list[uuid.UUID]) -> None:
    """성공한 시도의 기록을 지운다 (호출한 쪽이 커밋)."""
    db.execute(delete(AuthFailure).where(AuthFailure.id.in_(ids)))


def reserve_login(db: Session, login_id: str, ip: str) -> list[uuid.UUID]:
    window = timedelta(minutes=settings.login_lock_minutes)
    return _reserve(
        db,
        [
            ("login", _hash(login_id.strip().lower(), ip), settings.login_max_failures, window),
            ("login_ip", _hash(ip), settings.login_max_failures_per_ip, window),
        ],
        f"로그인 실패가 많아 잠시 막았습니다. "
        f"{settings.login_lock_minutes}분 뒤에 다시 시도해 주세요",
    )


def reserve_invite(db: Session, ip: str) -> list[uuid.UUID]:
    return _reserve(
        db,
        [("invite_ip", _hash(ip), settings.invite_max_failures_per_hour, timedelta(hours=1))],
        "초대 코드 확인이 잠시 막혀 있습니다. 한 시간 뒤에 다시 시도해 주세요",
    )
