from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import read_token

SESSION_COOKIE = "csn_session"

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, csn_session: Annotated[str | None, Cookie()] = None) -> User:
    user_id = read_token(csn_session) if csn_session else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
