import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

_hasher = PasswordHasher()
# 없는 아이디로 로그인할 때도 해시 검증 시간을 똑같이 쓰기 위한 값
_DUMMY_HASH = _hasher.hash("timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(hashed: str | None, password: str) -> bool:
    try:
        ok = _hasher.verify(hashed or _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return False
    return ok and hashed is not None


def create_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        # 로그아웃 시각과 비교하려고 초 미만까지 남긴다 (JWT NumericDate는 소수 허용)
        "iat": now.timestamp(),
        "exp": now + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def read_token(token: str) -> tuple[uuid.UUID, float] | None:
    """(사용자 id, 발급 시각 epoch 초)"""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "iat"]},
        )
        return uuid.UUID(payload["sub"]), float(payload["iat"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None
