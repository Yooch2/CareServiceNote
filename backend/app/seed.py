from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Recipient, User
from app.security import hash_password

# ponytail: 공개 데모용 고정 계정. 배포 단계에서 환경변수로 바꿀지 결정.
DEMO_LOGIN = "demo"
DEMO_PASSWORD = "demo1234"
DEMO_RECIPIENTS = ("김순자(가상)", "박영수(가상)", "이말순(가상)")


def seed(session: Session) -> None:
    if session.scalar(select(User).where(User.login_id == DEMO_LOGIN)) is None:
        session.add(
            User(
                login_id=DEMO_LOGIN,
                password_hash=hash_password(DEMO_PASSWORD),
                display_name="데모 요양보호사",
            )
        )
    existing = set(session.scalars(select(Recipient.name)))
    session.add_all(Recipient(name=n) for n in DEMO_RECIPIENTS if n not in existing)
    session.commit()


if __name__ == "__main__":
    with SessionLocal() as s:
        seed(s)
    print("데모 계정과 가상 수급자를 준비했습니다.")
