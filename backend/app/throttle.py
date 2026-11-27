"""로그인·초대 코드 시도 횟수 제한 (무작위 대입 방지).

- 로그인: 아이디별로 최근 LOGIN_LOCK_MINUTES 안 실패가 LOGIN_MAX_FAILURES번이면 막는다.
  없는 아이디도 같은 방식으로 세서, 막히는지로 아이디 존재를 알 수 없게 한다.
  성공하면 기록을 지운다.
- 초대 코드: 서비스 전체 실패가 한 시간에 INVITE_MAX_FAILURES_PER_HOUR번이면 막는다.
  코드가 약 49비트라 대입이 사실상 불가능하지만, 실패 요청을 쏟아붓는 것 자체를 멈춘다.

ponytail: IP별 제한은 프록시(Caddy → Next → API) 뒤에서 실제 IP를 믿을 수 있게 설정한 뒤 추가한다.
"""

import hashlib
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthFailure

_LOCK = 7_301_004  # advisory lock 번호 (키별 두 번째 값)
_INVITE_KEY = "invite"


def _key(login_id: str) -> str:
    return hashlib.sha256(login_id.strip().lower().encode()).hexdigest()


def _recent(db: Session, kind: str, key: str, window: timedelta) -> int:
    db.execute(select(func.pg_advisory_xact_lock(_LOCK, func.hashtext(f"{kind}:{key}"))))
    return (
        db.scalar(
            select(func.count())
            .select_from(AuthFailure)
            .where(
                AuthFailure.kind == kind,
                AuthFailure.key == key,
                AuthFailure.created_at > func.now() - window,
            )
        )
        or 0
    )


def check_login(db: Session, login_id: str) -> None:
    window = timedelta(minutes=settings.login_lock_minutes)
    if _recent(db, "login", _key(login_id), window) >= settings.login_max_failures:
        db.rollback()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"로그인 실패가 많아 잠시 막았습니다. "
            f"{settings.login_lock_minutes}분 뒤에 다시 시도해 주세요",
        )


def login_failed(db: Session, login_id: str) -> None:
    db.add(AuthFailure(kind="login", key=_key(login_id)))
    db.commit()


def login_succeeded(db: Session, login_id: str) -> None:
    db.execute(
        delete(AuthFailure).where(AuthFailure.kind == "login", AuthFailure.key == _key(login_id))
    )


def check_invite(db: Session) -> None:
    if (
        _recent(db, "invite", _INVITE_KEY, timedelta(hours=1))
        >= settings.invite_max_failures_per_hour
    ):
        db.rollback()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "초대 코드 확인이 잠시 막혀 있습니다. 잠시 뒤에 다시 시도해 주세요",
        )


def invite_failed(db: Session) -> None:
    db.add(AuthFailure(kind="invite", key=_INVITE_KEY))
    db.commit()
