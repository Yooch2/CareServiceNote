from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import throttle
from app.config import settings
from app.deps import SESSION_COOKIE, CurrentUser, DbSession
from app.invites import hash_code
from app.models import GuardianLink, Invite, Organization, User
from app.schemas import LoginIn, SignupIn, UserOut
from app.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_BAD_LOGIN = "아이디 또는 비밀번호가 올바르지 않습니다"
# 없는 코드·만료·이미 사용을 구분하지 않는다 (코드 추측에 단서를 주지 않으려고)
_BAD_INVITE = "초대 코드가 올바르지 않습니다"


def _set_session(response: Response, user: User) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_token(user.id),
        max_age=settings.jwt_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _claim_invite(db: Session, code: str) -> Invite:
    """쓸 수 있는 초대를 잠근다. 같은 코드로 동시에 가입하면 한 명만 통과한다."""
    invite = db.scalar(
        select(Invite)
        .where(
            Invite.code_hash == hash_code(code),
            Invite.used_at.is_(None),
            Invite.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if invite is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _BAD_INVITE)
    return invite


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def signup(body: SignupIn, db: DbSession, request: Request, response: Response) -> User:
    """센터를 만들면 기관 담당자, 초대 코드로 가입하면 초대에 적힌 역할이 된다."""
    attempt = (
        throttle.reserve_invite(db, throttle.client_ip(request))
        if body.invite_code is not None
        else []
    )
    user = User(
        login_id=body.login_id,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    try:
        if body.invite_code is not None:
            _join_by_invite(db, user, body.invite_code)
        else:
            org = Organization(name=body.center_name)
            db.add(org)
            db.flush()
            user.org_id, user.role = org.id, "manager"
            db.add(user)
        db.commit()
    except IntegrityError:
        db.rollback()  # 초대 코드도 쓰지 않은 상태로 돌아간다
        throttle.release(db, attempt)  # 코드는 맞았으므로 대입 시도로 세지 않는다
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 아이디입니다") from None
    throttle.release(db, attempt)
    db.commit()
    _set_session(response, user)
    return user


def _join_by_invite(db: Session, user: User, code: str) -> None:
    invite = _claim_invite(db, code)
    user.org_id, user.role = invite.org_id, invite.role
    db.add(user)
    db.flush()
    invite.used_at, invite.used_by = datetime.now(UTC), user.id
    if invite.role == "guardian":
        assert invite.recipient_id is not None and invite.categories is not None
        db.add(
            GuardianLink(
                recipient_id=invite.recipient_id,
                guardian_id=user.id,
                categories=invite.categories,
            )
        )


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, db: DbSession, request: Request, response: Response) -> User:
    attempt = throttle.reserve_login(db, body.login_id, throttle.client_ip(request))
    user = db.scalar(select(User).where(User.login_id == body.login_id))
    ok = verify_password(user.password_hash if user else None, body.password)
    if not ok or user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_LOGIN)  # 미리 기록한 실패가 남는다
    throttle.release(db, attempt)
    throttle.remember_success(db, body.login_id, throttle.client_ip(request))
    db.commit()
    _set_session(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
