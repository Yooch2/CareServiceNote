from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.deps import SESSION_COOKIE, CurrentUser, DbSession
from app.models import User
from app.schemas import LoginIn, SignupIn, UserOut
from app.security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_BAD_LOGIN = "아이디 또는 비밀번호가 올바르지 않습니다"


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


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def signup(body: SignupIn, db: DbSession, response: Response) -> User:
    user = User(
        login_id=body.login_id,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 아이디입니다") from None
    _set_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, db: DbSession, response: Response) -> User:
    user = db.scalar(select(User).where(User.login_id == body.login_id))
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_LOGIN)
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
