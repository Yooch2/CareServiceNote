"""로그인·초대 코드 시도 횟수 제한 (무작위 대입 방지).

시도를 확인하기 **전에** 실패 한 번으로 미리 기록하고(잠금 안에서 개수 확인 + 기록 + 커밋),
성공하면 그 기록을 지운다. 확인과 기록이 한 잠금 안에 있어 동시 요청으로 한도를 넘지 못한다.

- 로그인: (아이디 + 클라이언트 IP)별 15분 5번, IP별 15분 30번,
  그리고 IP와 상관없이 아이디별 한 시간 30번(여러 IP로 나눠 대입하는 경우).
  아이디별 상한에 닿아도, 최근 실패가 없는 IP의 시도는 통과시킨다. 그래서 남이 내 아이디로
  실패를 쌓아도 나는 로그인할 수 있고, 여러 IP로 나눈 대입은 새 IP마다 한 번씩만 시도할 수 있다.
  (CAPTCHA 없이 대입 방지와 잠금 악용 방지를 절충한 방식)
  없는 아이디도 같은 방식으로 세서 막히는지로 아이디 존재를 알 수 없다.
- 초대 코드: IP별 한 시간 10번. 전체 실패가 많으면 막지 않고 경고 로그만 남긴다.
- IPv6는 /64 단위로 묶어 센다 (한 가입자가 보통 /64 전체를 쓴다).

키는 해시만 저장한다 (아이디·IP 원문을 남기지 않음).
"""

import hashlib
import ipaddress
import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthFailure

log = logging.getLogger("csn.throttle")
_LOCK = 7_301_004  # advisory lock 번호 (키별 두 번째 값)


def _ip_bucket(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if addr.version == 6:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def client_ip(request: Request) -> str:
    """운영(TRUST_PROXY)에서는 Caddy가 넣은 X-Forwarded-For를, 아니면 직접 연결한 주소를 쓴다.

    API는 Caddy를 거쳐서만 닿게 배포한다(포트를 밖으로 열지 않음). Caddy는 신뢰하지 않는
    클라이언트가 보낸 X-Forwarded-For를 실제 접속 주소로 덮어쓴다.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if settings.trust_proxy and forwarded:
        return _ip_bucket(forwarded.split(",")[-1].strip())
    return _ip_bucket(request.client.host) if request.client else "unknown"


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


@dataclass(frozen=True)
class Rule:
    kind: str
    key: str
    limit: int
    window: timedelta
    # 이 규칙은 같은 요청의 다른 규칙 중 하나라도 최근 실패가 있을 때만 막는다
    # (아이디 전체 상한: 최근 실패가 없는 깨끗한 IP의 시도는 통과시켜 진짜 사용자가 잠기지 않게)
    only_if_dirty: bool = False


def _count(db: Session, rule: Rule) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(AuthFailure)
            .where(
                AuthFailure.kind == rule.kind,
                AuthFailure.key == rule.key,
                AuthFailure.created_at > func.now() - rule.window,
            )
        )
        or 0
    )


def _reserve(db: Session, rules: list[Rule], message: str) -> list[uuid.UUID]:
    """규칙을 모두 확인하고, 통과하면 실패 한 번씩 미리 기록한다."""
    for rule in sorted(rules, key=lambda r: (r.kind, r.key)):  # 같은 순서로 잠가 교착을 피한다
        db.execute(
            select(func.pg_advisory_xact_lock(_LOCK, func.hashtext(f"{rule.kind}:{rule.key}")))
        )
    counts = {rule.kind: _count(db, rule) for rule in rules}
    dirty = any(counts[r.kind] > 0 for r in rules if not r.only_if_dirty)
    for rule in rules:
        over = counts[rule.kind] >= rule.limit
        if over and (dirty or not rule.only_if_dirty):
            db.rollback()
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message)
    rows = [AuthFailure(kind=r.kind, key=r.key) for r in rules]
    db.add_all(rows)
    db.commit()  # 잠금이 풀리고, 이 시도는 실패로 세어진 상태
    return [r.id for r in rows]


def release(db: Session, ids: list[uuid.UUID]) -> None:
    """성공한 시도의 기록을 지운다 (호출한 쪽이 커밋)."""
    db.execute(delete(AuthFailure).where(AuthFailure.id.in_(ids)))


def reserve_login(db: Session, login_id: str, ip: str) -> list[uuid.UUID]:
    window = timedelta(minutes=settings.login_lock_minutes)
    account = login_id.strip().lower()
    return _reserve(
        db,
        [
            Rule("login", _hash(account, ip), settings.login_max_failures, window),
            Rule("login_ip", _hash(ip), settings.login_max_failures_per_ip, window),
            Rule(
                "login_account",
                _hash(account),
                settings.login_max_failures_per_account,
                timedelta(hours=1),
                only_if_dirty=True,
            ),
        ],
        f"로그인 실패가 많아 잠시 막았습니다. "
        f"{settings.login_lock_minutes}분 뒤에 다시 시도해 주세요",
    )


def reserve_invite(db: Session, ip: str) -> list[uuid.UUID]:
    """IP별로만 막는다. 전체 실패 수로 막으면 다른 사람의 올바른 코드까지 막혀서,
    전체 실패가 많을 때는 경고 로그만 남긴다(운영자가 알아챌 수 있게)."""
    hour = timedelta(hours=1)
    ids = _reserve(
        db,
        [Rule("invite_ip", _hash(ip), settings.invite_max_failures_per_hour, hour)],
        "초대 코드 확인이 잠시 막혀 있습니다. 한 시간 뒤에 다시 시도해 주세요",
    )
    total = db.scalar(
        select(func.count())
        .select_from(AuthFailure)
        .where(AuthFailure.kind == "invite_ip", AuthFailure.created_at > func.now() - hour)
    )
    if (total or 0) >= settings.invite_failures_alert_per_hour:
        log.warning("invite code failures in the last hour: %s (possible guessing)", total)
    return ids
