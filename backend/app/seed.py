from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Assignment, Consent, GuardianLink, Organization, Recipient, User
from app.security import hash_password

# ponytail: 공개 데모용 고정 계정. 배포 단계에서 환경변수로 바꿀지 결정.
DEMO_ORG = "햇살방문요양센터(가상)"
DEMO_PASSWORD = "demo1234"
DEMO_LOGIN = "demo"
DEMO_USERS = (
    ("manager", "manager", "데모 기관 담당자"),
    (DEMO_LOGIN, "caregiver", "데모 요양보호사"),
    ("demo2", "caregiver", "데모 요양보호사2"),  # 배정 없음: 담당 교체 시연용
    ("family", "guardian", "데모 보호자"),
)
DEMO_RECIPIENTS = ("김순자(가상)", "박영수(가상)", "이말순(가상)")
GUARDIAN_OF = "김순자(가상)"
GUARDIAN_CATEGORIES = ["followup", "remark"]


def seed(session: Session) -> None:
    """데모 센터·계정·가상 수급자·배정·동의를 만든다. 여러 번 실행해도 같다."""
    org = session.scalar(select(Organization).where(Organization.name == DEMO_ORG))
    if org is None:
        org = Organization(name=DEMO_ORG)
        session.add(org)
        session.flush()

    users: dict[str, User] = {}
    for login_id, role, name in DEMO_USERS:
        user = session.scalar(select(User).where(User.login_id == login_id))
        if user is None:
            user = User(login_id=login_id, password_hash=hash_password(DEMO_PASSWORD))
            session.add(user)
        user.org_id, user.role, user.display_name, user.active = org.id, role, name, True
        users[login_id] = user
    session.flush()

    recipients: dict[str, Recipient] = {}
    for name in DEMO_RECIPIENTS:
        recipient = session.scalar(
            select(Recipient).where(Recipient.org_id == org.id, Recipient.name == name)
        )
        if recipient is None:
            recipient = Recipient(org_id=org.id, name=name)
            session.add(recipient)
            session.flush()
        recipients[name] = recipient
        _ensure_assignment(session, recipient, users[DEMO_LOGIN], users["manager"])
        _ensure_consent(session, recipient, "health_record", users["manager"])

    guardian_of = recipients[GUARDIAN_OF]
    _ensure_consent(session, guardian_of, "guardian_share", users["manager"])
    family = users["family"]
    if session.scalar(select(GuardianLink).where(GuardianLink.guardian_id == family.id)) is None:
        session.add(
            GuardianLink(
                recipient_id=guardian_of.id,
                guardian_id=family.id,
                categories=GUARDIAN_CATEGORIES,
            )
        )
    session.commit()


def _ensure_assignment(session: Session, recipient: Recipient, caregiver: User, by: User) -> None:
    found = session.scalar(
        select(Assignment).where(
            Assignment.recipient_id == recipient.id,
            Assignment.caregiver_id == caregiver.id,
            Assignment.ended_at.is_(None),
        )
    )
    if found is None:
        session.add(
            Assignment(recipient_id=recipient.id, caregiver_id=caregiver.id, created_by=by.id)
        )


def _ensure_consent(session: Session, recipient: Recipient, kind: str, by: User) -> None:
    found = session.scalar(
        select(Consent).where(
            Consent.recipient_id == recipient.id,
            Consent.kind == kind,
            Consent.withdrawn_at.is_(None),
        )
    )
    if found is None:
        session.add(
            Consent(
                recipient_id=recipient.id, kind=kind, granted_on=date.today(), recorded_by=by.id
            )
        )


if __name__ == "__main__":
    with SessionLocal() as s:
        seed(s)
    print("데모 센터, 계정, 가상 수급자를 준비했습니다.")
